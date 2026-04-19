"""Wake → Gemini Live session → close loop.

Holds together the lifecycle of one conversational turn:

  wake fires  →  open session
              →  send initial camera frame
              →  stream mic PCM
              →  play received audio
              →  handle tool calls
              →  silence watchdog closes session
  back to wake
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from robot import ui
from robot.config import Config
from robot.live.audio_io import MicStream, SpeakerStream, verify_devices
from robot.live.dispatcher import ToolDispatcher
from robot.live.session import GeminiLiveSession
from robot.live.tools_schema import ALL as TOOLS
from robot.perception.camera import Camera
from robot.perception.wake import Wake
from robot.tools.gpio_signal import GpioService
from robot.tools.memory import MemoryStore
from robot.tools.motion import MotionService
from robot.tools.reminder import ReminderService
from robot.tools.time_tool import handle as handle_time
from robot.tools.speak import handle as handle_speak
from robot.tools.vision import VisionService

logger = logging.getLogger(__name__)


@dataclass
class Services:
    camera: Camera
    wake: Wake
    motion: MotionService
    gpio: GpioService
    memory: MemoryStore


async def run(cfg: Config, services: Services, shutdown: asyncio.Event) -> None:
    verify_devices(cfg.input_device, cfg.output_device)
    session_count = 0

    while not shutdown.is_set():
        ui.wake_prompt()
        wake_task = asyncio.create_task(services.wake.wait())
        shutdown_task = asyncio.create_task(shutdown.wait())
        done, pending = await asyncio.wait(
            {wake_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if shutdown.is_set():
            break

        session_count += 1
        ui.session_start(session_count)
        try:
            await _run_one_session(cfg, services, shutdown)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            ui.error(f"Session crashed: {exc}")
            logger.exception("Session crashed; returning to wake loop")
        ui.session_end(session_count)


async def _run_one_session(
    cfg: Config, services: Services, shutdown: asyncio.Event
) -> None:
    speaker = SpeakerStream(device=cfg.output_device)
    speaker.start()

    audio_chunks_received = [0]

    async def play_audio(pcm: bytes) -> None:
        audio_chunks_received[0] += 1
        ui.audio_out_chunk(len(pcm))
        await speaker.play(pcm)

    async def speak_text(text: str) -> None:
        # Fallback speaker for reminders fired outside a live session.
        logger.info("[reminder text] %s", text)

    reminder_service = ReminderService(speak_text)

    async def on_tool_call(name: str, args: dict) -> dict:
        ui.tool_call(name, args)
        result = await dispatcher(name, args)
        ui.tool_result(name, result)
        return result

    async def send_image_to_session(jpeg: bytes) -> None:
        await session.send_image(jpeg)

    vision_service = VisionService(services.camera, send_image_to_session)

    dispatcher = ToolDispatcher(
        {
            "speak": handle_speak,
            "describe_scene": vision_service.handle,
            "remember": services.memory.remember,
            "get_time": handle_time,
            "set_reminder": reminder_service.schedule,
            "gpio_signal": services.gpio.handle,
            "move": services.motion.handle,
        }
    )

    mic_ref: list[MicStream | None] = [None]

    def on_state_change(new_state: str) -> None:
        # Mute mic while Gemini speaks / a tool runs → prevents speaker
        # echo from tripping the server VAD and interrupting Gemini.
        mic = mic_ref[0]
        if mic is None:
            return
        should_mute = new_state == "gemini_speaking" or new_state.startswith("tool:")
        mic.set_muted(should_mute)
        if should_mute:
            ui.info(f"[dim]🔇 mic muted ({new_state})[/]")
        else:
            ui.info(f"[dim]🔈 mic unmuted ({new_state})[/]")

    session = GeminiLiveSession(
        api_key=cfg.google_api_key,
        model=cfg.gemini_model,
        system_instruction=_build_system_instruction(cfg, services.memory),
        tools=TOOLS,
        on_audio_out=play_audio,
        on_tool_call=on_tool_call,
        on_state_change=on_state_change,
    )

    try:
        async with session:
            # Initial visual context: one camera frame per session open.
            try:
                jpeg = services.camera.capture_jpeg()
                await session.send_image(jpeg)
                ui.camera_frame_sent(len(jpeg), source="session open")
                if len(jpeg) < 8000:
                    ui.info(
                        f"⚠  initial frame only {len(jpeg)} bytes — camera "
                        "may be dark/uninitialised; ask \"what do you see?\" "
                        "for a fresh frame"
                    )
            except Exception:
                logger.exception("Initial camera frame failed; continuing")

            mic = MicStream(session.send_audio_chunk, device=cfg.input_device)
            mic.start()
            mic_ref[0] = mic
            ui.mic_started()
            ui.speaker_started()
            ui.state_listening()

            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(mic.pump(), name="mic_pump")
                    tg.create_task(session.recv_loop(), name="recv_loop")
                    tg.create_task(
                        _session_watchdog(cfg, shutdown), name="watchdog"
                    )
                    tg.create_task(
                        _heartbeat(session, shutdown), name="heartbeat"
                    )
            except* Exception as group:
                for exc in group.exceptions:
                    logger.warning("Session task exited: %r", exc)
    finally:
        mic = mic_ref[0]
        if mic is not None:
            mic.stop()
        mic_ref[0] = None
        await speaker.cancel()
        speaker.stop()
        reminder_service.cancel_all()
        if audio_chunks_received[0] > 0:
            ui.audio_out_complete()


async def _heartbeat(session: GeminiLiveSession, shutdown: asyncio.Event) -> None:
    """Pulse a status line every 3 seconds while waiting in a quiet state.

    Only emits when the state has been unchanged for >=3 seconds, so active
    conversation doesn't get spammed.
    """
    last_mic = 0
    last_audio = 0
    while not shutdown.is_set():
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=3.0)
            return
        except asyncio.TimeoutError:
            pass
        elapsed = session.state_elapsed()
        mic = session.mic_chunks_sent
        audio = session.audio_chunks_received
        # Emit only in "waiting" states OR if counters moved since last tick
        quiet_state = session.current_state in ("listening", "")
        moved = (mic != last_mic) or (audio != last_audio)
        if elapsed >= 3.0 and (quiet_state or moved):
            ui.heartbeat(
                session.current_state or "opening",
                elapsed,
                mic,
                audio,
            )
        last_mic, last_audio = mic, audio


async def _session_watchdog(cfg: Config, shutdown: asyncio.Event) -> None:
    """Close the session after a max lifetime or on shutdown."""
    deadline = asyncio.get_running_loop().time() + cfg.max_session_seconds
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            logger.info(
                "[watchdog] max_session_seconds=%ds reached — closing",
                cfg.max_session_seconds,
            )
            raise _WatchdogStop()
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=remaining)
            logger.info("[watchdog] shutdown requested")
            raise _WatchdogStop()
        except asyncio.TimeoutError:
            continue


class _WatchdogStop(Exception):
    """Internal signal to unwind the TaskGroup cleanly."""


def _build_system_instruction(cfg: Config, memory: MemoryStore) -> str:
    preamble = cfg.system_prompt
    mem = memory.snapshot()
    if mem:
        lines = [f"- {k}: {v}" for k, v in mem.items()]
        preamble += "\n\nPersistent memory:\n" + "\n".join(lines)
    return preamble
