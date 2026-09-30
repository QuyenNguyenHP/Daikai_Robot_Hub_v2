from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from typing import List, Literal

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.robot_battery import RobotBatteryService
from backend.robot_control import (
    RobotControlBusyError,
    RobotControlError,
    RobotControlService,
    RobotControlStateError,
)
from backend.robot_audio import (
    MAX_TEXT_LENGTH,
    RobotAudioBusyError,
    RobotAudioError,
    RobotAudioService,
)
from backend.robot_services import (
    RobotServiceBusyError,
    RobotServiceError,
    RobotServiceManager,
    RobotServiceProtectedError,
)
from backend.robot_teleoperation import (
    RobotTeleoperationService,
    TeleoperationError,
    TeleoperationStateError,
)
from backend.video_streaming import (
    VideoStreamingError,
    VideoStreamingService,
    VideoStreamingStateError,
)
from backend.voice_ai import VoiceAIClient, VoiceAIError


from backend.robot_stereo_detection import (
    RobotStereoDetectionService, RobotStereoError, RobotStereoStateError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.robot_battery = RobotBatteryService()
    app.state.robot_control = RobotControlService()
    app.state.robot_audio = RobotAudioService()
    app.state.voice_ai = VoiceAIClient()
    app.state.robot_services = RobotServiceManager()
    app.state.robot_teleoperation = RobotTeleoperationService()
    app.state.camera_start_lock = threading.Lock()
    app.state.video_streaming = VideoStreamingService()
    app.state.robot_stereo_detection = RobotStereoDetectionService()
    app.state.robot_battery.start()
    try:
        yield
    finally:
        app.state.robot_battery.stop()
        app.state.robot_control.stop()
        app.state.robot_audio.stop()
        app.state.robot_teleoperation.shutdown()
        app.state.video_streaming.shutdown()
        app.state.robot_stereo_detection.stop()


app = FastAPI(
    title="Daikai Robot Hub API",
    version="1.0.0",
    description="Robot control and monitoring API for the React web application.",
    lifespan=lifespan,
)

origins = [
    value.strip()
    for value in os.getenv(
        "FR_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if value.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def robot_audio(request: Request) -> RobotAudioService:
    return request.app.state.robot_audio


def voice_ai(request: Request) -> VoiceAIClient:
    return request.app.state.voice_ai


def robot_battery(request: Request) -> RobotBatteryService:
    return request.app.state.robot_battery


def robot_control(request: Request) -> RobotControlService:
    return request.app.state.robot_control


def robot_services(request: Request) -> RobotServiceManager:
    return request.app.state.robot_services


def robot_teleoperation(request: Request) -> RobotTeleoperationService:
    return request.app.state.robot_teleoperation


def video_streaming(request: Request) -> VideoStreamingService:
    return request.app.state.video_streaming


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class RobotTextChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(min_items=1, max_items=30)


class LedRequest(BaseModel):
    red: int = Field(ge=0, le=255)
    green: int = Field(ge=0, le=255)
    blue: int = Field(ge=0, le=255)
    keep_on: bool = False


class ControlRequest(BaseModel):
    action: Literal[
        "stance",
        "zero_torque",
        "enable",
        "disable",
        "forward",
        "backward",
        "left",
        "right",
        "turn_left",
        "turn_right",
        "stop",
        "lie_to_stand",
        "stand_to_lie",
        "crankshaft_start",
        "crankshaft_stop",
        "teleoperation_stop",
    ]
    arm: Literal["left", "right", "both"] = "right"
    speed_deg_s: float = Field(default=120.0, ge=100.0, le=150.0)
    hold_seconds: float = Field(default=0.05, ge=0.05, le=0.5)


class ServiceSwitchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    enabled: bool


class TeleoperationStartRequest(BaseModel):
    input_mode: Literal["hand", "controller"] = "controller"


@app.get("/api/health")
def health(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "robot_battery": robot_battery(request).status(),
        "robot_control": robot_control(request).status(),
        "robot_audio": robot_audio(request).status(),
    }


@app.get("/api/robot/battery")
def robot_battery_status(request: Request) -> dict[str, object]:
    return robot_battery(request).status()


@app.websocket("/api/robot/battery/ws")
async def robot_battery_status_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    battery: RobotBatteryService = websocket.app.state.robot_battery
    try:
        while True:
            await websocket.send_json(battery.status())
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        return


@app.get("/api/robot/control/status")
def robot_control_status(request: Request) -> dict[str, object]:
    return robot_control(request).status()


@app.get("/api/video-stream/status")
def video_stream_status(request: Request) -> dict[str, object]:
    return video_streaming(request).status()


@app.post("/api/video-stream/start")
def start_video_stream(request: Request) -> dict[str, object]:
    try:
        services = robot_services(request).list().get("services", [])
        stereo_service = next(
            (item for item in services if item.get("name") == "stereo_patch_pc1"),
            None,
        )
        if stereo_service is None:
            raise VideoStreamingStateError(
                "Required robot service 'stereo_patch_pc1' was not reported."
            )
        if not stereo_service.get("enabled"):
            raise VideoStreamingStateError(
                "Turn on robot service 'stereo_patch_pc1' before streaming."
            )
        with request.app.state.camera_start_lock:
            if robot_stereo_detection(request).status()["running"]:
                raise VideoStreamingStateError("Stop object distance detection before starting the video viewer.")
            return video_streaming(request).start()
    except RobotServiceBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except VideoStreamingStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except VideoStreamingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/video-stream/feed")
def video_stream_feed(request: Request) -> StreamingResponse:
    try:
        stream = video_streaming(request).stream()
        first_chunk = next(stream)
    except VideoStreamingStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except VideoStreamingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    def content():
        yield first_chunk
        yield from stream

    return StreamingResponse(
        content(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/video-stream/stop")
def stop_video_stream(request: Request) -> dict[str, object]:
    try:
        return video_streaming(request).stop()
    except VideoStreamingStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except VideoStreamingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/robot/services")
def list_robot_services(request: Request) -> dict[str, object]:
    try:
        return robot_services(request).list()
    except RobotServiceBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/robot/services/switch")
def switch_robot_service(
    request: Request,
    payload: ServiceSwitchRequest,
) -> dict[str, object]:
    try:
        return robot_services(request).switch(payload.name, payload.enabled)
    except (RobotServiceBusyError, RobotServiceProtectedError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/robot/teleoperation/status")
def teleoperation_status(request: Request) -> dict[str, object]:
    return robot_teleoperation(request).status()


@app.post("/api/robot/teleoperation/start")
def start_teleoperation(
    request: Request, payload: TeleoperationStartRequest
) -> dict[str, object]:
    try:
        mode = robot_control(request).mode()
        if mode.get("fsm_id") != 811:
            raise TeleoperationStateError(
                "Teleoperation can only launch when the robot is in locomotion mode 811; "
                f"current mode is {mode.get('display', 'unknown')}."
            )
        return robot_teleoperation(request).start(payload.input_mode)
    except RobotControlBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotControlError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except TeleoperationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TeleoperationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/robot/teleoperation/tracking/start")
def begin_teleoperation_tracking(request: Request) -> dict[str, object]:
    try:
        return robot_teleoperation(request).begin_tracking()
    except TeleoperationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TeleoperationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/robot/teleoperation/stop")
def stop_teleoperation(request: Request) -> dict[str, object]:
    try:
        result = robot_teleoperation(request).stop()
        control = robot_control(request)
        if not control.network_interface:
            # Teleoperation is fixed to eth10, so use the same interface for
            # the immediate post-teleop FSM transition when the backend was
            # launched without UNITREE_NETWORK_INTERFACE.
            control = RobotControlService(network_interface="eth10")
        mode = control.execute("teleoperation_stop")
        return {**result, "robot_mode": mode.get("last_fsm_id")}
    except TeleoperationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TeleoperationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except RobotControlBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotControlError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/robot/mode")
def robot_mode(request: Request) -> dict[str, object]:
    try:
        return robot_control(request).mode()
    except RobotControlBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotControlError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.websocket("/api/robot/mode/ws")
async def robot_mode_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    control: RobotControlService = websocket.app.state.robot_control
    try:
        while True:
            try:
                payload = control.mode()
                payload["error"] = None
            except RobotControlBusyError as error:
                payload = {"error": str(error), "control_busy": True}
            except RobotControlError as error:
                payload = {"error": str(error), "control_busy": False}
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        return


@app.post("/api/robot/control")
def control_robot(request: Request, payload: ControlRequest) -> dict[str, object]:
    try:
        return robot_control(request).execute(
            payload.action,
            arm=payload.arm,
            speed_deg_s=payload.speed_deg_s,
            hold_seconds=payload.hold_seconds,
        )
    except (RobotControlBusyError, RobotControlStateError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotControlError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/robot/speech/status")
def robot_speech_status(request: Request) -> dict[str, object]:
    return robot_audio(request).status()


@app.post("/api/robot/speak")
def speak_on_robot(request: Request, payload: SpeechRequest) -> dict[str, object]:
    try:
        return robot_audio(request).speak(payload.text)
    except RobotAudioBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotAudioError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/robot/voice-chat/status")
def robot_voice_chat_status(request: Request) -> dict[str, object]:
    return voice_ai(request).status()


@app.post("/api/robot/text-chat")
async def robot_text_chat(
    request: Request,
    payload: RobotTextChatRequest,
) -> dict[str, object]:
    if payload.messages[-1].role != "user":
        raise HTTPException(
            status_code=422,
            detail="The last chat message must be from the user.",
        )

    ai_client = voice_ai(request)
    audio_service = robot_audio(request)
    messages = [message.dict() for message in payload.messages]

    def chat_and_speak() -> dict[str, object]:
        answer = ai_client.chat(messages)
        playback = audio_service.speak_english(answer)
        return {"text": answer, **playback}

    try:
        return await run_in_threadpool(chat_and_speak)
    except RobotAudioBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except VoiceAIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RobotAudioError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/robot/voice-chat")
async def robot_voice_chat(request: Request) -> dict[str, object]:
    content_type = request.headers.get("content-type", "application/octet-stream")
    session_id = request.headers.get("x-voice-session", "robot-console").strip()
    if not session_id or len(session_id) > 100:
        raise HTTPException(status_code=422, detail="Invalid voice session ID.")
    audio = await request.body()
    if not audio or len(audio) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Recorded audio is empty or exceeds 25 MB.",
        )
    ai_client = voice_ai(request)
    audio_service = robot_audio(request)

    def converse_and_play() -> dict[str, object]:
        result = ai_client.converse(audio, content_type, session_id)
        playback = audio_service.play_wav(result.pop("wav"))
        return {**result, **playback}

    try:
        return await run_in_threadpool(converse_and_play)
    except RobotAudioBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except VoiceAIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RobotAudioError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/robot/led")
def set_robot_led(request: Request, payload: LedRequest) -> dict[str, object]:
    try:
        return robot_audio(request).set_led(
            payload.red,
            payload.green,
            payload.blue,
            payload.keep_on,
        )
    except RobotAudioBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotAudioError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def robot_stereo_detection(request: Request) -> RobotStereoDetectionService:
    return request.app.state.robot_stereo_detection


class StereoClassesRequest(BaseModel):
    classes: list[str] = Field(min_length=1, max_length=30)


@app.get("/api/robot/stereo/status")
def robot_stereo_status(request: Request) -> dict[str, object]:
    return robot_stereo_detection(request).status()


@app.websocket("/api/robot/stereo/ws")
async def robot_stereo_status_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    detector: RobotStereoDetectionService = websocket.app.state.robot_stereo_detection
    try:
        while True:
            await websocket.send_json(detector.status())
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError is raised when the ASGI server has already closed the
        # connection before the next status update is sent.
        return


@app.post("/api/robot/stereo/start")
def start_robot_stereo(request: Request) -> dict[str, object]:
    detector = robot_stereo_detection(request)
    try:
        with request.app.state.camera_start_lock:
            if video_streaming(request).status()["running"]:
                raise HTTPException(status_code=409, detail="Stop the video viewer before starting object distance detection.")
            detector.start()
    except RobotStereoError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return detector.status()


@app.post("/api/robot/stereo/stop")
def stop_robot_stereo(request: Request) -> dict[str, object]:
    detector = robot_stereo_detection(request)
    detector.stop()
    return detector.status()


@app.post("/api/robot/stereo/classes")
def set_robot_stereo_classes(
    request: Request,
    payload: StereoClassesRequest,
) -> dict[str, object]:
    try:
        return robot_stereo_detection(request).set_classes(payload.classes)
    except RobotStereoStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotStereoError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/robot/stereo/stream/{view}")
def robot_stereo_stream(
    request: Request,
    view: Literal["detection", "depth"],
) -> StreamingResponse:
    detector = robot_stereo_detection(request)
    return StreamingResponse(
        detector.mjpeg_stream(view),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
