"""Client for the external speech-to-speech AI service."""

from __future__ import annotations

import base64
import binascii
import os
from typing import Dict, List

import requests

DEFAULT_VOICE_AI_SERVER_URL = "http://192.168.0.51:8000"



class VoiceAIError(RuntimeError):
    """Raised when the configured voice AI service cannot answer."""


class VoiceAIClient:
    def __init__(self) -> None:
        self.base_url = os.getenv(
            "VOICE_AI_SERVER_URL", DEFAULT_VOICE_AI_SERVER_URL
        ).strip().rstrip("/")
        self.api_key = os.getenv("VOICE_AI_API_KEY", "").strip()
        try:
            self.timeout_seconds = max(
                10.0, float(os.getenv("VOICE_AI_TIMEOUT_SECONDS", "180"))
            )
        except ValueError:
            self.timeout_seconds = 180.0

    def status(self) -> dict[str, object]:
        return {
            "configured": bool(self.base_url),
            "server_url": self.base_url or None,
        }

    def chat(self, messages: List[Dict[str, str]]) -> str:
        if not self.base_url:
            raise VoiceAIError("VOICE_AI_SERVER_URL is not configured.")
        if not messages:
            raise VoiceAIError("At least one chat message is required.")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json={"messages": messages},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise VoiceAIError(f"Could not reach the voice AI server: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise VoiceAIError(
                f"Voice AI server returned an invalid response ({response.status_code})."
            ) from exc
        if not response.ok:
            detail = payload.get("detail", f"HTTP {response.status_code}")
            raise VoiceAIError(f"Voice AI request failed: {detail}")
        try:
            answer = str(payload["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise VoiceAIError("Voice AI response did not contain an answer.") from exc
        if not answer:
            raise VoiceAIError("Voice AI returned an empty answer.")
        return answer

    def converse(
        self,
        audio: bytes,
        content_type: str,
        session_id: str,
    ) -> dict[str, object]:
        if not self.base_url:
            raise VoiceAIError("VOICE_AI_SERVER_URL is not configured.")
        if not audio:
            raise VoiceAIError("Recorded audio is empty.")

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(
                f"{self.base_url}/v1/voice/chat",
                headers=headers,
                files={"audio": ("question.webm", audio, content_type)},
                data={"session_id": session_id, "response_format": "json"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise VoiceAIError(f"Could not reach the voice AI server: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise VoiceAIError(
                f"Voice AI server returned an invalid response ({response.status_code})."
            ) from exc
        if not response.ok:
            detail = payload.get("detail", f"HTTP {response.status_code}")
            raise VoiceAIError(f"Voice AI request failed: {detail}")

        try:
            wav = base64.b64decode(payload["audio_base64"], validate=True)
        except (KeyError, ValueError, binascii.Error) as exc:
            raise VoiceAIError("Voice AI response did not contain valid WAV audio.") from exc
        return {
            "transcript": str(payload.get("transcript", "")),
            "text": str(payload.get("text", "")),
            "language": payload.get("language"),
            "wav": wav,
        }
