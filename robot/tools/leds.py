"""set_leds() tool — Gemini-controlled LED output.

Gives Gemini direct control over the breadboard LEDs so it can
express emotions, play games, signal alerts, or do anything creative.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

LED_NAMES = ("green", "blue", "yellow", "red")

DEFAULT_PIN_MAP: dict[str, int] = {
    "green": 17,
    "blue": 22,
    "yellow": 27,
    "red": 23,
}


class Gpio(Protocol):
    def set(self, pin: int, state: bool) -> None: ...


class LedToolService:
    def __init__(self, gpio: Gpio, pin_map: dict[str, int] | None = None) -> None:
        self._gpio = gpio
        self._pins = pin_map or DEFAULT_PIN_MAP
        self._current: dict[str, bool] = {name: False for name in self._pins}
        self._pattern_task: asyncio.Task | None = None

    def _set_led(self, name: str, state: bool) -> None:
        pin = self._pins.get(name)
        if pin is not None:
            self._gpio.set(pin, state)
            self._current[name] = state

    def _all_off(self) -> None:
        for name in self._pins:
            self._set_led(name, False)

    def _cancel_pattern(self) -> None:
        if self._pattern_task is not None and not self._pattern_task.done():
            self._pattern_task.cancel()
            self._pattern_task = None

    async def handle(self, args: dict) -> dict:
        self._cancel_pattern()

        leds = args.get("leds")
        pattern = args.get("pattern")

        if pattern is not None:
            return await self._run_pattern(pattern)

        if leds is None:
            return {"error": "Provide 'leds' (object) or 'pattern' (list of frames)."}

        if not isinstance(leds, dict):
            return {"error": "'leds' must be an object like {\"green\": true, \"blue\": false}"}

        for name, state in leds.items():
            if name not in self._pins:
                return {"error": f"Unknown LED '{name}'. Available: {list(self._pins.keys())}"}
            self._set_led(name, bool(state))

        return {"ok": True, "leds": dict(self._current)}

    async def _run_pattern(self, frames: list) -> dict:
        if not isinstance(frames, list) or len(frames) == 0:
            return {"error": "'pattern' must be a non-empty list of frames."}
        if len(frames) > 50:
            return {"error": "Pattern too long (max 50 frames)."}

        async def _play() -> None:
            repeat = False
            for frame in frames:
                if not isinstance(frame, dict):
                    continue
                leds = frame.get("leds", {})
                duration_ms = frame.get("duration_ms", 300)
                repeat = frame.get("repeat", False)

                for name, state in leds.items():
                    if name in self._pins:
                        self._set_led(name, bool(state))

                await asyncio.sleep(max(50, min(5000, int(duration_ms))) / 1000.0)

            if not repeat:
                self._all_off()

        self._pattern_task = asyncio.create_task(_play())

        return {"ok": True, "frames": len(frames), "status": "playing"}

    def close(self) -> None:
        self._cancel_pattern()
        self._all_off()
