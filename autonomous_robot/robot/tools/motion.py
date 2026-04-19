"""move() handler — drives wheels for a bounded duration."""

from __future__ import annotations

import asyncio
import logging

from robot.hardware.motors import Motors

logger = logging.getLogger(__name__)

VALID_DIRECTIONS = {"forward", "backward", "left", "right", "stop"}


class MotionService:
    def __init__(self, motors: Motors) -> None:
        self._motors = motors

    async def handle(self, args: dict) -> dict:
        direction = args.get("direction", "stop")
        if direction not in VALID_DIRECTIONS:
            return {"error": f"direction must be one of {sorted(VALID_DIRECTIONS)}"}
        try:
            speed = float(args.get("speed", 0.5))
        except (TypeError, ValueError):
            return {"error": "speed must be a number"}
        speed = max(0.0, min(1.0, speed))
        try:
            duration_ms = int(args.get("duration_ms", 1000))
        except (TypeError, ValueError):
            return {"error": "duration_ms must be an integer"}
        duration_ms = max(0, min(10_000, duration_ms))

        action = getattr(self._motors, direction)
        action(speed) if direction != "stop" else action()

        if direction != "stop" and duration_ms > 0:
            await asyncio.sleep(duration_ms / 1000.0)
            self._motors.stop()

        return {"ok": True, "direction": direction, "speed": speed, "duration_ms": duration_ms}
