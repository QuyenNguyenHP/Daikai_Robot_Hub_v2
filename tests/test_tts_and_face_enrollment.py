"""Native TTS and photo registration; no real robot or identity database writes."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from backend.robot_audio import RobotAudioService, RobotAudioError, RobotAudioBusyError
from backend.face_database import load_database, save_database
from backend.face_enrollment import FaceEnrollmentService, FaceEnrollmentError, MAX_IMAGE_BYTES
from backend.vision_faces import VisionFaces


class NativeTTSTests(unittest.TestCase):
    def test_native_tts_options_and_rpc_failures(self):
        service = RobotAudioService(network_interface='test-interface')
        client = Mock()
        service._audio_client = Mock(return_value=client)
        client.SetVolume.return_value = 0
        client.TtsMaker.return_value = 0
        result = service.speak('  Hello   R1  ', speaker_id=1, volume=70)
        client.SetVolume.assert_called_once_with(70)
        client.TtsMaker.assert_called_once_with('Hello R1', 1)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['volume'], 70)
        client.SetVolume.return_value = 42
        with self.assertRaises(RobotAudioError):
            service.speak('Hello')
        self.assertEqual(client.TtsMaker.call_count, 1)
        client.SetVolume.return_value = 0
        client.TtsMaker.return_value = 42
        with self.assertRaises(RobotAudioError):
            service.speak('Hello')
        self.assertFalse(service.status()['busy'])

    def test_validation_and_shared_audio_lock(self):
        service = RobotAudioService(network_interface='test-interface')
        for text, options in [('', {}), ('x' * 201, {}), ('Hello', {'volume': 101}),
                              ('Hello', {'speaker_id': 9}), ('Hello', {'speaker_id': 1.5})]:
            with self.assertRaises(RobotAudioError):
                service.speak(text, **options)
        service._lock.acquire()
        try:
            with self.assertRaises(RobotAudioBusyError):
                service.speak('Hello')
        finally:
            service._lock.release()


class PhotoEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'embeddings.npz'
        self.environment = patch.dict(os.environ, {'VISION_FACE_DATABASE': str(self.path)})
        self.environment.start()
        self.service = FaceEnrollmentService()
        self.service._vision = SimpleNamespace(detector=Mock(), recognizer=Mock())
        self.service._vision.detector.detect.return_value = (None, np.array([[1, 2, 20, 20]]))
        self.service._vision.recognizer.feature.return_value = np.eye(1, 128, dtype=np.float32)
        self.decode = patch('cv2.imdecode', return_value=np.zeros((80, 80, 3), dtype=np.uint8))
        self.decode.start()

    def tearDown(self):
        self.decode.stop()
        self.environment.stop()
        self.directory.cleanup()

    def test_appends_new_samples_and_keeps_existing_people(self):
        save_database(self.path, ['Existing'], np.eye(1, 128, dtype=np.float32))
        result = self.service.enroll('  New Person ', [('one.jpg', b'photo'), ('two.jpg', b'photo')])
        self.assertEqual(result['accepted'], 2)
        self.assertTrue(result['saved'])
        names, features = load_database(self.path)
        self.assertEqual(names, ['Existing', 'New Person', 'New Person'])
        self.assertEqual(features.shape, (3, 128))
        self.assertEqual(len(self.service.people()['people']), 2)
        self.service.enroll('New Person', [('three.jpg', b'photo')])
        self.assertEqual(len(load_database(self.path)[0]), 4)

    def test_rejects_no_face_and_multiple_faces_without_overwriting_database(self):
        save_database(self.path, ['Existing'], np.eye(1, 128, dtype=np.float32))
        before = self.path.read_bytes()
        self.service._vision.detector.detect.side_effect = [(None, None), (None, [[1], [2]])]
        result = self.service.enroll('Someone', [('no-face.jpg', b'photo'), ('group.jpg', b'photo')])
        self.assertFalse(result['saved'])
        self.assertEqual(len(result['rejected']), 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_partial_success_and_invalid_files(self):
        self.service._vision.detector.detect.side_effect = [(None, None), (None, [[1, 2, 20, 20]])]
        result = self.service.enroll('Someone', [('empty.jpg', b''), ('no-face.jpg', b'photo'), ('good.jpg', b'photo')])
        self.assertEqual(result['accepted_files'], ['good.jpg'])
        self.assertEqual(len(result['rejected']), 2)
        self.assertEqual(load_database(self.path)[0], ['Someone'])
        for name, files in [('../name', [('a.jpg', b'p')]), ('', [('a.jpg', b'p')]), ('Name', [])]:
            with self.assertRaises(FaceEnrollmentError):
                self.service.enroll(name, files)

    def test_live_recognition_reloads_changed_database(self):
        vision = VisionFaces.__new__(VisionFaces)
        vision.database = self.path
        vision._database_version = None
        vision.reload_database()
        self.assertEqual(vision.names, [])
        self.service.enroll('New Person', [('one.jpg', b'photo')])
        vision.reload_database()
        self.assertEqual(vision.names, ['New Person'])
        self.assertAlmostEqual(float(np.linalg.norm(vision.embeddings[0])), 1)

    def test_multipart_api_and_limits_without_starting_robot_lifespan(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        app.state.face_enrollment = self.service
        client = TestClient(app)
        response = client.post('/api/vision/enroll', data={'name': 'Photo Person'},
                               files=[('images', ('photo.jpg', b'image', 'image/jpeg'))])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['saved'])
        self.assertEqual(client.get('/api/vision/people').json()['people'][0]['name'], 'Photo Person')
        bad = client.post('/api/vision/enroll', data={'name': '../invalid'},
                          files=[('images', ('photo.jpg', b'image', 'image/jpeg'))])
        self.assertEqual(bad.status_code, 422)
        unsupported = client.post('/api/vision/enroll', data={'name': 'Test'},
                                  files=[('images', ('text.txt', b'not an image', 'text/plain'))])
        self.assertEqual(unsupported.status_code, 422)
        oversized = client.post('/api/vision/enroll', data={'name': 'Test'},
                               files=[('images', ('large.jpg', b'x' * (MAX_IMAGE_BYTES + 1), 'image/jpeg'))])
        self.assertEqual(oversized.status_code, 413)
        app.state.robot_audio = Mock()
        app.state.robot_audio.speak.return_value = {'accepted': True}
        speech = client.post('/api/robot/speak', json={'text': 'Hello', 'speaker_id': 1, 'volume': 70})
        self.assertEqual(speech.status_code, 200)
        app.state.robot_audio.speak.assert_called_once_with('Hello', speaker_id=1, volume=70)
        self.assertEqual(client.post('/api/robot/speak', json={'text': 'Hello', 'volume': 101}).status_code, 422)
        client.close()


if __name__ == '__main__':
    unittest.main()
