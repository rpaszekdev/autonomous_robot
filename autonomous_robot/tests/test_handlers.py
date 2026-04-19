import asyncio
import logging

import pytest

from robot.hardware.gpio import MockGpio
from robot.hardware.motors import MockMotors
from robot.tools.gpio_signal import GpioService
from robot.tools.motion import MotionService
from robot.tools.reminder import ReminderService
from robot.tools.time_tool import handle as handle_time


@pytest.mark.asyncio
async def test_time_handler():
    result = await handle_time({})
    assert "iso" in result and "human" in result


@pytest.mark.asyncio
async def test_motion_clamps_speed_and_stops():
    motors = MockMotors()
    service = MotionService(motors)
    result = await service.handle({"direction": "forward", "speed": 5.0, "duration_ms": 10})
    assert result["ok"]
    assert result["speed"] == 1.0


@pytest.mark.asyncio
async def test_motion_rejects_invalid_direction():
    result = await MotionService(MockMotors()).handle({"direction": "diagonal"})
    assert "error" in result


@pytest.mark.asyncio
async def test_gpio_auto_reset():
    gpio = MockGpio()
    result = await GpioService(gpio).handle({"pin": 17, "state": True, "duration_ms": 10})
    assert result == {"ok": True, "pin": 17, "state": True}


@pytest.mark.asyncio
async def test_reminder_fires_after_delay():
    spoken: list[str] = []

    async def speak(text: str) -> None:
        spoken.append(text)

    service = ReminderService(speak)
    r = await service.schedule({"message": "stretch", "delay_seconds": 0})
    assert r["ok"]
    await asyncio.sleep(0.05)
    assert spoken == ["stretch"]
