from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, IPvAnyAddress

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.robot_battery = RobotBatteryService()
    app.state.robot_control = RobotControlService()
    app.state.robot_audio = RobotAudioService()
    app.state.robot_services = RobotServiceManager()
    app.state.robot_teleoperation = RobotTeleoperationService()
    app.state.video_streaming = VideoStreamingService()
    app.state.robot_battery.start()
    try:
        yield
    finally:
        app.state.robot_battery.stop()
        app.state.robot_control.stop()
        app.state.robot_audio.stop()
        app.state.robot_teleoperation.shutdown()
        app.state.video_streaming.shutdown()


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


class LedRequest(BaseModel):
    red: int = Field(ge=0, le=255)
    green: int = Field(ge=0, le=255)
    blue: int = Field(ge=0, le=255)
    keep_on: bool = False


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100)


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


class VideoStreamingStartRequest(BaseModel):
    destination_ip: IPvAnyAddress


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
def start_video_stream(
    request: Request, payload: VideoStreamingStartRequest
) -> dict[str, object]:
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
        return video_streaming(request).start(str(payload.destination_ip))
    except RobotServiceBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RobotServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except VideoStreamingStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except VideoStreamingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


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


@app.post("/api/robot/volume")
def set_robot_volume(request: Request, payload: VolumeRequest) -> dict[str, object]:
    try:
        return robot_audio(request).set_volume(payload.volume)
    except RobotAudioBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
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
