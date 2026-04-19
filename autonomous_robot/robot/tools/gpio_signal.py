"""gpio_signal() handler — set a GPIO pin with optional auto-reset."""

from __future__ import annotations

import asyncio
import logging

from robot.hardware.gpio import Gpio

logger = logging.getLogger(__name__)


class GpioService:
    def __init__(self, gpio: Gpio) -> None:
        self._gpio = gpio

    async def handle(self, args: dict) -> dict:
        try:
            pin = int(args["pin"])
            state = bool(args["state"])
        except (KeyError, TypeError, ValueError):
            return {"error": "pin (int) and state (bool) are required"}

        duration = args.get("duration_ms")
        self._gpio.set(pin, state)

        if duration is not None:
            try:
                duration_ms = max(0, int(duration))
            except (TypeError, ValueError):
                return {"error": "duration_ms must be an integer"}
            if duration_ms > 0:
                await asyncio.sleep(duration_ms / 1000.0)
                self._gpio.set(pin, not state)

        return {"ok": True, "pin": pin, "state": state}
