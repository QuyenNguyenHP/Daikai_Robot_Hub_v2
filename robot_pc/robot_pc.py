#!/usr/bin/env python3
"""Robot-side gateway: ESP button -> R1 mic -> PC1 AI -> R1 speaker."""

from __future__ import annotations

import argparse
import asyncio
import collections
import fcntl
import json
import logging
import math
import os
import socket
import struct
import time
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, WSMsgType, web
from dotenv import load_dotenv

MULTICAST_GROUP = "239.168.123.161"
MULTICAST_PORT = 5555
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
SIOCGIFADDR = 0x8915
PLAY_CHUNK_SIZE = 32_000  # one second of 16-kHz PCM16
APP_NAME = "r1_local_ai"

LOG = logging.getLogger("robot-pc")


def message(kind: str, **values: Any) -> str:
    """Create a JSON WebSocket message."""
    return json.dumps({"type": kind, **values}, ensure_ascii=False)


def parse_message(data: str) -> dict[str, Any]:
    """Parse and validate a JSON WebSocket message."""
    value = json.loads(data)
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("WebSocket message must be an object containing 'type'")
    return value


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw mono PCM16 data in a WAV container."""
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


def pcm_rms(pcm: bytes) -> float:
    """Return RMS amplitude of little-endian signed PCM16."""
    usable = len(pcm) - len(pcm) % SAMPLE_WIDTH
    if not usable:
        return 0.0
    samples = struct.unpack(f"<{usable // SAMPLE_WIDTH}h", pcm[:usable])
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


async def run_blocking(function, *args):
    """Run blocking SDK/audio work on Python 3.8 and newer."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, function, *args)


@dataclass
class Settings:
    interface: str
    pc1_url: str
    silence_seconds: float
    threshold: float
    speech_timeout: float
    max_seconds: float
    volume: int | None
    greeting_text: str
    greeting_wait_seconds: float
    no_speech_response: str


def interface_ipv4(interface: str) -> str:
    encoded = interface.encode()
    if len(encoded) >= 16:
        raise ValueError(f"Interface name is too long: {interface!r}")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        response = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, struct.pack("256s", encoded[:15]))
    return socket.inet_ntoa(response[20:24])


def open_microphone_socket(local_ip: str) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", MULTICAST_PORT))
    membership = struct.pack("=4s4s", socket.inet_aton(MULTICAST_GROUP), socket.inet_aton(local_ip))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.settimeout(0.25)
    return sock


def record_until_silence(settings: Settings) -> bytes:
    """Record after speech begins, ending after the configured continuous silence."""
    local_ip = interface_ipv4(settings.interface)
    LOG.info("Listening to R1 microphone via %s (%s)", settings.interface, local_ip)
    audio = bytearray()
    pre_roll: collections.deque[bytes] = collections.deque()
    pre_roll_bytes = int(0.4 * SAMPLE_RATE * SAMPLE_WIDTH)
    began = time.monotonic()
    speech_started = False
    last_voice = began
    packet_count = 0
    peak_rms = 0.0

    with open_microphone_socket(local_ip) as receiver:
        while True:
            now = time.monotonic()
            if now - began >= settings.max_seconds:
                break
            if not speech_started and now - began >= settings.speech_timeout:
                if packet_count == 0:
                    raise TimeoutError(
                        f"No microphone UDP packets received on {settings.interface} "
                        f"from {MULTICAST_GROUP}:{MULTICAST_PORT}"
                    )
                raise TimeoutError(
                    f"No speech detected in {settings.speech_timeout:g}s; "
                    f"received {packet_count} packets, peak RMS={peak_rms:.0f}, "
                    f"threshold={settings.threshold:.0f}"
                )
            try:
                packet, _ = receiver.recvfrom(65_535)
            except socket.timeout:
                if speech_started and time.monotonic() - last_voice >= settings.silence_seconds:
                    break
                continue

            packet = packet[: len(packet) - len(packet) % SAMPLE_WIDTH]
            if not packet:
                continue
            packet_count += 1
            now = time.monotonic()
            level = pcm_rms(packet)
            peak_rms = max(peak_rms, level)
            voiced = level >= settings.threshold
            if not speech_started:
                pre_roll.append(packet)
                while sum(map(len, pre_roll)) > pre_roll_bytes:
                    pre_roll.popleft()
                if voiced:
                    speech_started = True
                    last_voice = now
                    audio.extend(b"".join(pre_roll))
                    pre_roll.clear()
            else:
                audio.extend(packet)
                if voiced:
                    last_voice = now
                elif now - last_voice >= settings.silence_seconds:
                    break
    if not audio:
        raise RuntimeError("Microphone returned no usable speech")
    LOG.info("Captured %.2f seconds", len(audio) / SAMPLE_WIDTH / SAMPLE_RATE)
    return bytes(audio)


class RobotGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clients: set[web.WebSocketResponse] = set()
        self.conversation_lock = asyncio.Lock()

    async def broadcast(self, kind: str, **values: object) -> None:
        payload = message(kind, **values)
        dead = []
        for ws in self.clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        self.clients.difference_update(dead)

    async def esp_socket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        await ws.send_str(message("ready"))
        LOG.info("ESP32 connected from %s", request.remote)
        try:
            async for incoming in ws:
                if incoming.type == WSMsgType.TEXT:
                    try:
                        data = parse_message(incoming.data)
                        if data["type"] == "record":
                            asyncio.create_task(self.run_conversation())
                        elif data["type"] == "ping":
                            await ws.send_str(message("pong"))
                    except Exception as exc:
                        await ws.send_str(message("error", detail=str(exc)))
        finally:
            self.clients.discard(ws)
            LOG.info("ESP32 disconnected: %s", request.remote)
        return ws

    async def run_conversation(self) -> None:
        if self.conversation_lock.locked():
            await self.broadcast("busy", detail="A request is already running")
            return
        async with self.conversation_lock:
            try:
                await self.broadcast("greeting", text=self.settings.greeting_text)
                await run_blocking(self.say_greeting)
                await self.broadcast("listening")
                try:
                    pcm = await run_blocking(record_until_silence, self.settings)
                except TimeoutError as exc:
                    LOG.warning("%s; requesting retry prompt from PC1", exc)
                    await self.broadcast("thinking")
                    reply_text, reply_pcm = await self.ask_pc1_tts(self.settings.no_speech_response)
                    await self.broadcast("speaking", text=reply_text)
                    await run_blocking(self.play_audio, reply_pcm)
                    await self.broadcast("ready", text=reply_text)
                    return
                await self.broadcast("thinking")
                reply_text, reply_pcm = await self.ask_pc1(pcm_to_wav(pcm))
                await self.broadcast("speaking", text=reply_text)
                await run_blocking(self.play_audio, reply_pcm)
                await self.broadcast("ready", text=reply_text)
            except Exception as exc:
                LOG.exception("Conversation failed")
                await self.broadcast("error", detail=str(exc))

    async def ask_pc1_tts(self, text: str) -> tuple[str, bytes]:
        """Ask PC1 to synthesize a fixed message without invoking Whisper or the LLM."""
        timeout = __import__("aiohttp").ClientTimeout(total=180)
        async with ClientSession(timeout=timeout) as session:
            async with session.ws_connect(self.settings.pc1_url, heartbeat=20) as ws:
                await ws.send_str(message("tts", text=text))
                metadata = await ws.receive()
                if metadata.type != WSMsgType.TEXT:
                    raise RuntimeError("PC1 did not return TTS metadata")
                info = parse_message(metadata.data)
                if info["type"] == "error":
                    raise RuntimeError(f"PC1: {info.get('detail', 'unknown error')}")
                if info["type"] != "response":
                    raise RuntimeError(f"Unexpected PC1 response: {info['type']}")
                audio = await ws.receive()
                if audio.type != WSMsgType.BINARY:
                    raise RuntimeError("PC1 did not return TTS audio")
                return str(info.get("text", text)), bytes(audio.data)

    def say_greeting(self) -> None:
        """Play a short greeting before opening the microphone recording."""
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

        ChannelFactoryInitialize(0, self.settings.interface)
        client = AudioClient()
        client.SetTimeout(10.0)
        client.Init()
        if self.settings.volume is not None:
            result = client.SetVolume(self.settings.volume)
            if result != 0:
                raise RuntimeError(f"SetVolume failed before greeting: {result}")
        result = client.TtsMaker(self.settings.greeting_text, 1)
        code = result[0] if isinstance(result, tuple) else result
        if code != 0:
            raise RuntimeError(f"Greeting TtsMaker failed: {code}")
        time.sleep(self.settings.greeting_wait_seconds)

    async def ask_pc1(self, wav: bytes) -> tuple[str, bytes]:
        timeout = __import__("aiohttp").ClientTimeout(total=180)
        async with ClientSession(timeout=timeout) as session:
            async with session.ws_connect(self.settings.pc1_url, heartbeat=20) as ws:
                await ws.send_str(message("audio", format="wav", size=len(wav)))
                await ws.send_bytes(wav)
                metadata = await ws.receive()
                if metadata.type != WSMsgType.TEXT:
                    raise RuntimeError("PC1 did not return response metadata")
                info = parse_message(metadata.data)
                if info["type"] == "error":
                    raise RuntimeError(f"PC1: {info.get('detail', 'unknown error')}")
                if info["type"] != "response":
                    raise RuntimeError(f"Unexpected PC1 response: {info['type']}")
                audio = await ws.receive()
                if audio.type != WSMsgType.BINARY:
                    raise RuntimeError("PC1 did not return PCM audio")
                return str(info.get("text", "")), bytes(audio.data)

    def play_audio(self, pcm: bytes) -> None:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

        ChannelFactoryInitialize(0, self.settings.interface)
        client = AudioClient()
        client.SetTimeout(10.0)
        client.Init()
        if self.settings.volume is not None:
            result = client.SetVolume(self.settings.volume)
            if result != 0:
                raise RuntimeError(f"SetVolume failed: {result}")
        stream_id = str(int(time.time() * 1000))
        for offset in range(0, len(pcm), PLAY_CHUNK_SIZE):
            chunk = pcm[offset : offset + PLAY_CHUNK_SIZE]
            result = client.PlayStream(APP_NAME, stream_id, chunk)
            code = result[0] if isinstance(result, tuple) else result
            if code != 0:
                client.PlayStop(APP_NAME)
                raise RuntimeError(f"PlayStream failed: {code}")
            time.sleep(len(chunk) / (SAMPLE_RATE * SAMPLE_WIDTH))
        client.PlayStop(APP_NAME)


def parse_args() -> argparse.Namespace:
    load_dotenv(Path(__file__).resolve().with_name(".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-interface", default=os.getenv("ROBOT_NETWORK_INTERFACE", "eth0"))
    parser.add_argument("--pc1-url", default=os.getenv("PC1_WS_URL", "ws://192.168.1.10:8766/ai"))
    parser.add_argument("--listen", default=os.getenv("ROBOT_SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ROBOT_SERVER_PORT", "8765")))
    parser.add_argument("--silence-seconds", type=float, default=float(os.getenv("VAD_SILENCE_SECONDS", "2.5")))
    parser.add_argument("--threshold", type=float, default=float(os.getenv("VAD_RMS_THRESHOLD", "500")), help="PCM RMS voice threshold")
    parser.add_argument("--speech-timeout", type=float, default=float(os.getenv("VAD_SPEECH_TIMEOUT", "10")))
    parser.add_argument("--max-seconds", type=float, default=float(os.getenv("VAD_MAX_SECONDS", "45")))
    volume = os.getenv("ROBOT_VOLUME", "").strip()
    parser.add_argument("--volume", type=int, default=int(volume) if volume else None)
    parser.add_argument("--greeting-text", default=os.getenv("GREETING_TEXT", "Hello"))
    parser.add_argument("--greeting-wait-seconds", type=float,
                        default=float(os.getenv("GREETING_WAIT_SECONDS", "2.0")))
    parser.add_argument("--no-speech-response",
                        default=os.getenv("NO_SPEECH_RESPONSE", "Please speak again."))
    parser.add_argument("--verbose", action="store_true", default=os.getenv("LOG_VERBOSE", "false").lower() in {"1", "true", "yes"})
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.volume is not None and not 0 <= args.volume <= 100:
        raise SystemExit("--volume must be between 0 and 100")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    gateway = RobotGateway(Settings(args.network_interface, args.pc1_url, args.silence_seconds,
                                    args.threshold, args.speech_timeout, args.max_seconds, args.volume,
                                    args.greeting_text, args.greeting_wait_seconds,
                                    args.no_speech_response))
    app = web.Application()
    app.router.add_get("/ws", gateway.esp_socket)
    app.router.add_get("/health", lambda _request: web.json_response({"ok": True, "port": args.port}))
    LOG.info("ESP32 WebSocket endpoint: ws://%s:%s/ws", args.listen, args.port)
    web.run_app(app, host=args.listen, port=args.port)


if __name__ == "__main__":
    main()
