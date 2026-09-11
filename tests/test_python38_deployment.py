"""Compatibility checks; no CUDA hardware or robot connection required."""
import ast
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.robot_stereo_detection import _set_model_classes

ROOT = Path(__file__).resolve().parents[1]


class Python38DeploymentTests(unittest.TestCase):
    def test_backend_annotations_can_be_evaluated_on_python38(self):
        # Postponed annotations can parse on 3.8 but still fail when FastAPI
        # evaluates them. Reject newer runtime annotation constructs as well.
        for path in (ROOT / 'backend').rglob('*.py'):
            tree = ast.parse(path.read_text(), feature_version=8)
            for node in ast.walk(tree):
                annotation = None
                if isinstance(node, (ast.arg, ast.AnnAssign)):
                    annotation = node.annotation
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    annotation = node.returns
                if annotation is None:
                    continue
                for part in ast.walk(annotation):
                    self.assertFalse(isinstance(part, ast.BinOp) and isinstance(part.op, ast.BitOr), str(path))
                    if isinstance(part, ast.Subscript) and isinstance(part.value, ast.Name):
                        self.assertNotIn(part.value.id, {'list', 'dict', 'tuple', 'set', 'type'}, str(path))

    def test_fastapi_schema_and_class_validation(self):
        from pydantic import ValidationError
        from backend.main import app, StereoClassesRequest
        self.assertIn('/api/robot/stereo/start', app.openapi()['paths'])
        self.assertEqual(StereoClassesRequest(classes=['person']).classes, ['person'])
        with self.assertRaises(ValidationError):
            StereoClassesRequest(classes=[])

    def test_legacy_clip_uses_local_weights_and_requested_device(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            cached = source / 'weights' / 'clip' / 'ViT-B-32.pt'
            cached.parent.mkdir(parents=True)
            cached.touch()
            encoder = object()
            clip = types.ModuleType('clip')
            clip.load = Mock(return_value=(encoder, None))
            nn = types.ModuleType('ultralytics.nn')
            ultra = types.ModuleType('ultralytics')
            model = Mock()
            with patch.dict(sys.modules, {'ultralytics': ultra, 'ultralytics.nn': nn, 'clip': clip}):
                _set_model_classes(model, ['chair'], source, 'cuda:0')
            clip.load.assert_called_once_with(str(cached), device='cuda:0', download_root=str(cached.parent))
            self.assertIs(model.model.clip_model, encoder)
            model.set_classes.assert_called_once_with(['chair'])

    def test_legacy_clip_downloads_to_expected_cache_when_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            clip = types.ModuleType('clip')
            clip.load = Mock(return_value=(object(), None))
            with patch.dict(sys.modules, {'ultralytics': types.ModuleType('ultralytics'),
                                        'ultralytics.nn': types.ModuleType('ultralytics.nn'), 'clip': clip}):
                _set_model_classes(Mock(), ['chair'], source, 'cpu')
            clip.load.assert_called_once_with('ViT-B/32', device='cpu', download_root=str(source / 'weights' / 'clip'))

    def test_modern_encoder_keeps_existing_loading_path(self):
        nn = types.ModuleType('ultralytics.nn')
        nn.text_model = types.SimpleNamespace()
        clip = types.ModuleType('clip')
        clip.load = Mock()
        model = Mock()
        with patch.dict(sys.modules, {'ultralytics': types.ModuleType('ultralytics'), 'ultralytics.nn': nn, 'clip': clip}):
            _set_model_classes(model, ['person'], Path('/models'), 'cuda:0')
        self.assertEqual(nn.text_model.WEIGHTS_DIR, Path('/models/weights'))
        clip.load.assert_not_called()
        model.set_classes.assert_called_once_with(['person'])


if __name__ == '__main__':
    unittest.main()
