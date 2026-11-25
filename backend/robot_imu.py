"""Read-only R1 IMU telemetry from the low-state DDS topic."""
import math
import os
import time

from backend.robot_battery import RobotBatteryService


class RobotIMUService(RobotBatteryService):
    """Reuse the telemetry subscription lifecycle with the R1 LowState type."""

    def __init__(self, network_interface=None, topic=None):
        super().__init__(network_interface, topic or os.getenv("UNITREE_IMU_TOPIC", "rt/lowstate"))

    def _message_type(self):
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
        return LowState_

    def _handle_message(self, message):
        imu = message.imu_state
        reading = {
            "rpy_deg": [math.degrees(float(v)) for v in imu.rpy],
            "gyroscope_rad_s": [float(v) for v in imu.gyroscope],
            "accelerometer_m_s2": [float(v) for v in imu.accelerometer],
            "quaternion_wxyz": [float(v) for v in imu.quaternion],
            "temperature_c": int(imu.temperature),
            "updated_at": time.time(),
        }
        if not all(math.isfinite(v) for key, values in reading.items()
                   for v in (values if isinstance(values, list) else [values])):
            return
        with self._lock:
            self._reading = reading
            self._last_update_at = reading["updated_at"]
            self._message_count += 1
            self._state = "connected"
            self._error = None

    def status(self):
        result = super().status()
        result["imu"] = result.pop("battery")
        return result
