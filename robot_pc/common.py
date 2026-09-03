"""Wire protocol and small audio helpers shared by both PCs."""

from __future__ import annotations

import json
import math
import struct
import wave
from io import BytesIO
from typing import Any

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2


def message(kind: str, **values: Any) -> str:
    return json.dumps({"type": kind, **values}, ensure_ascii=False)


def parse_message(data: str) -> dict[str, Any]:
    value = json.loads(data)
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("WebSocket message must be an object containing 'type'")
    return value


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


def pcm_rms(pcm: bytes) -> float:
    """Return RMS amplitude of little-endian signed PCM16 without dependencies."""
    usable = len(pcm) - len(pcm) % 2
    if not usable:
        return 0.0
    samples = struct.unpack(f"<{usable // 2}h", pcm[:usable])
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))

