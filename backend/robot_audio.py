"""Unitree R1 audio client for speech playback and RGB LED control."""

from __future__ import annotations

import os
import threading

from backend.unitree_dds import UNITREE_DDS_INIT_LOCK


MAX_TEXT_LENGTH = 200
SPEECH_VOLUME = 100


class RobotAudioError(RuntimeError):
    """Raised when robot audio or LED control fails."""


class RobotAudioBusyError(RobotAudioError):
    """Raised when another audio-client request is already running."""


class RobotAudioService:
    def __init__(self, network_interface: str | None = None) -> None:
        self.network_interface = (
            network_interface or os.getenv("UNITREE_NETWORK_INTERFACE", "")
        ).strip()
        self._lock = threading.Lock()
        self._client = None
        self._speaker_id = self._read_speaker_id()
        self._led_rgb: tuple[int, int, int] | None = None
        self._led_state_lock = threading.Lock()
        self._led_keep_on = False
        self._led_stop_event = threading.Event()
        self._led_thread: threading.Thread | None = None
        try:
            interval = float(os.getenv("ROBOT_LED_KEEPALIVE_SECONDS", "0.5"))
        except ValueError:
            interval = 0.5
        self._led_keepalive_seconds = min(max(interval, 0.2), 10.0)

    @staticmethod
    def _read_speaker_id() -> int:
        try:
            speaker_id = int(os.getenv("ROBOT_TTS_SPEAKER_ID", "1"))
        except ValueError:
            return 1
        return speaker_id if 0 <= speaker_id <= 4 else 1

    def status(self) -> dict[str, object]:
        return {
            "configured": bool(self.network_interface),
            "available": bool(self.network_interface),
            "busy": self._lock.locked(),
            "tts_backend": "unitree_tts_maker",
            "speaker_id": self._speaker_id,
            "volume": SPEECH_VOLUME,
            "led_rgb": list(self._led_rgb) if self._led_rgb is not None else None,
            "led_keep_on": self._led_keep_on,
            "led_keepalive_seconds": self._led_keepalive_seconds,
        }

    def _validate(self, text: str) -> str:
        normalized = " ".join(text.strip().split())
        if not normalized:
            raise RobotAudioError("Speech text cannot be empty.")
        if len(normalized) > MAX_TEXT_LENGTH:
            raise RobotAudioError(
                f"Speech text cannot exceed {MAX_TEXT_LENGTH} characters."
            )
        if not self.network_interface:
            raise RobotAudioError("UNITREE_NETWORK_INTERFACE is not configured.")
        return normalized

    def _audio_client(self):
        if self._client is not None:
            return self._client
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
        except ImportError as exc:
            raise RobotAudioError(f"Unitree SDK could not be imported: {exc}") from exc

        try:
            with UNITREE_DDS_INIT_LOCK:
                ChannelFactoryInitialize(0, self.network_interface)
                client = AudioClient()
                client.SetTimeout(10.0)
                client.Init()
        except Exception as exc:
            raise RobotAudioError(
                f"Could not initialize the Unitree audio client: {exc}"
            ) from exc
        self._client = client
        return client

    def _ensure_led_thread(self) -> None:
        if self._led_thread is not None and self._led_thread.is_alive():
            return
        self._led_stop_event.clear()
        self._led_thread = threading.Thread(
            target=self._led_keepalive_loop,
            name="unitree-led-keepalive",
            daemon=True,
        )
        self._led_thread.start()

    def _led_keepalive_loop(self) -> None:
        while not self._led_stop_event.wait(self._led_keepalive_seconds):
            with self._led_state_lock:
                keep_on = self._led_keep_on
                rgb = self._led_rgb
            if not keep_on or rgb is None or not self._lock.acquire(blocking=False):
                continue
            try:
                self._audio_client().LedControl(*rgb)
            except Exception:
                # Retry temporary RPC failures at the next interval.
                pass
            finally:
                self._lock.release()

    def stop(self) -> None:
        self._led_stop_event.set()
        thread = self._led_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def set_led(
        self,
        red: int,
        green: int,
        blue: int,
        keep_on: bool = False,
    ) -> dict[str, object]:
        rgb = (red, green, blue)
        if any(isinstance(value, bool) or not 0 <= value <= 255 for value in rgb):
            raise RobotAudioError("LED RGB values must be integers from 0 to 255.")
        if not self.network_interface:
            raise RobotAudioError("UNITREE_NETWORK_INTERFACE is not configured.")
        if not self._lock.acquire(blocking=False):
            raise RobotAudioBusyError(
                "The robot audio service is busy; wait for speech to finish."
            )
        try:
            code = self._audio_client().LedControl(red, green, blue)
            if code != 0:
                raise RobotAudioError(f"LedControl failed with code {code}.")
            with self._led_state_lock:
                self._led_rgb = rgb
                self._led_keep_on = keep_on
            if keep_on:
                self._ensure_led_thread()
            return {
                "updated": True,
                "red": red,
                "green": green,
                "blue": blue,
                "keep_on": keep_on,
            }
        except RobotAudioError:
            raise
        except Exception as exc:
            raise RobotAudioError(f"Could not set the robot LED: {exc}") from exc
        finally:
            self._lock.release()

    def speak(
        self,
        text: str,
        speaker_id: int | None = None,
    ) -> dict[str, object]:
        normalized = self._validate(text)
        selected_speaker_id = self._speaker_id if speaker_id is None else speaker_id
        if isinstance(selected_speaker_id, bool) or not 0 <= selected_speaker_id <= 4:
            raise RobotAudioError("Speaker ID must be an integer from 0 to 4.")
        if not self._lock.acquire(blocking=False):
            raise RobotAudioBusyError("The robot is already speaking.")
        try:
            client = self._audio_client()
            code = client.SetVolume(SPEECH_VOLUME)
            if code != 0:
                raise RobotAudioError(f"SetVolume failed with code {code}.")
            code = client.TtsMaker(normalized, selected_speaker_id)
            if code != 0:
                raise RobotAudioError(f"TtsMaker failed with code {code}.")
            return {
                "spoken": True,
                "text": normalized,
                "speaker_id": selected_speaker_id,
                "volume": SPEECH_VOLUME,
            }
        except RobotAudioError:
            raise
        except Exception as exc:
            raise RobotAudioError(f"Robot TTS request failed: {exc}") from exc
        finally:
            self._lock.release()
