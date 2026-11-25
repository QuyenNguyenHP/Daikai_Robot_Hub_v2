"""Firmware action discovery and dispatch tests; all robot clients are mocked."""
import time
import unittest
from unittest.mock import Mock, patch

from backend.robot_control import (
    RobotControlService, RobotControlError, RobotControlBusyError, RobotControlStateError,
)


class RobotArmActionTests(unittest.TestCase):
    def setUp(self):
        self.service = RobotControlService(network_interface='test-interface')
        self.loco = Mock()
        self.arm = Mock()
        self.arm.GetActionList.return_value = (0, {'data': [{'actions': [
            {'id': 7, 'name': 'wave_above_head'}, {'id': 99, 'name': 'release_arm'},
            {'id': 17, 'name': 'clamp'}, {'id': 'invalid', 'name': 'invalid'},
        ]}]})
        self.arm.ExecuteAction.return_value = 0
        self.service._client_instance = Mock(return_value=self.loco)
        self.service._arm_client_instance = Mock(return_value=self.arm)
        self.service._fsm_id = Mock(return_value=811)

    def test_discovers_all_firmware_actions_without_moving(self):
        result = self.service.available_arm_actions()
        self.assertEqual([a['id'] for a in result['arm_actions']], [7, 17, 99])
        self.arm.ExecuteAction.assert_not_called()
        self.service._client_instance.assert_not_called()

    def test_executes_advertised_id_and_enforces_cooldown(self):
        result = self.service.execute_arm_action(7)
        self.arm.ExecuteAction.assert_called_once_with(7)
        self.assertTrue(result['ok'])
        self.assertEqual(result['action_name'], 'wave_above_head')
        self.assertGreater(result['arm_action_cooldown_seconds'], 0)
        with self.assertRaises(RobotControlBusyError):
            self.service.execute_arm_action(17)
        with self.assertRaises(RobotControlBusyError):
            self.service.execute('crankshaft_start')
        with self.assertRaises(RobotControlBusyError):
            self.service.execute_velocity(0.1, 0, 0, 0.1)
        self.arm.ExecuteAction.assert_called_once()

    def test_requires_exact_fsm_811_and_does_not_switch_modes(self):
        for fsm_id in [0, 4, 816]:
            self.service._fsm_id.return_value = fsm_id
            with self.assertRaises(RobotControlStateError):
                self.service.execute_arm_action(7)
        self.arm.ExecuteAction.assert_not_called()
        self.loco.SetFsmId.assert_not_called()

    def test_rejects_unadvertised_action_and_failed_discovery(self):
        with self.assertRaises(RobotControlStateError):
            self.service.execute_arm_action(123)
        self.arm.GetActionList.return_value = (42, None)
        with self.assertRaises(RobotControlError):
            self.service.execute_arm_action(7)
        self.arm.ExecuteAction.assert_not_called()
        self.assertFalse(self.service.status()['busy'])

    def test_serializes_with_other_control_and_polishing(self):
        self.service._lock.acquire()
        try:
            with self.assertRaises(RobotControlBusyError):
                self.service.execute_arm_action(7)
            with self.assertRaises(RobotControlBusyError):
                self.service.available_arm_actions()
        finally:
            self.service._lock.release()
        self.service._polishing_thread = Mock()
        self.service._polishing_thread.is_alive.return_value = True
        with self.assertRaises(RobotControlBusyError):
            self.service.execute_arm_action(7)
        self.arm.ExecuteAction.assert_not_called()

    def test_failed_rpc_keeps_cooldown_but_stop_is_available(self):
        self.arm.ExecuteAction.side_effect = TimeoutError('No response')
        with self.assertRaises(RobotControlError):
            self.service.execute_arm_action(7)
        self.assertGreater(self.service.status()['arm_action_cooldown_seconds'], 0)
        self.loco.SetVelocity.return_value = 0
        with patch.object(self.service, '_require_locomotion'):
            self.assertTrue(self.service.execute('stop')['ok'])
        self.loco.SetVelocity.assert_called_once()
        self.service._arm_action_ready_at = time.monotonic() - 1
        self.arm.ExecuteAction.side_effect = None
        self.arm.ExecuteAction.return_value = 0
        self.assertEqual(self.service.execute_arm_action(99)['action_name'], 'release_arm')


if __name__ == '__main__':
    unittest.main()
