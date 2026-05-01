"""LED status indicator — maps robot states to LED patterns.

Green  (GPIO 17) = listening (mic active)
Yellow (GPIO 27) = thinking / tool call (blinks)
Blue   (GPIO 22) = Gemini speaking
All off          = idle / wake word waiting

Uses lgpio directly (required for Pi 5 RP1 chip).
Silently disabled if lgpio is unavailable (e.g. running on Mac).
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

GREEN  = 17
YELLOW = 27
BLUE   = 22
ALL_PINS = [GREEN, YELLOW, BLUE]
GPIOCHIP = 4  # RP1 on Pi 5; use 0 for Pi 4 and earlier


class LedController:
    def __init__(self) -> None:
        self._stop_blink = threading.Event()
        self._blink_thread: threading.Thread | None = None
        self._h = None
        self._lg = None

        try:
            import lgpio
            self._lg = lgpio
            self._h = lgpio.gpiochip_open(GPIOCHIP)
            for pin in ALL_PINS:
                lgpio.gpio_claim_output(self._h, pin, 0)
            logger.info("LEDs ready on gpiochip%d (pins %s)", GPIOCHIP, ALL_PINS)
        except Exception:
            logger.warning("LEDs unavailable — running without GPIO", exc_info=False)

    @property
    def _available(self) -> bool:
        return self._h is not None

    def set_state(self, state: str) -> None:
        if not self._available:
            return
        self._cancel_blink()

        if state == "listening":
            self._write(green=True, yellow=False, blue=False)
        elif state == "gemini_speaking":
            self._write(green=False, yellow=False, blue=True)
        elif state.startswith("tool:"):
            self._write(green=False, yellow=False, blue=False)
            self._start_blink(YELLOW, interval=0.25)
        else:
            # idle / opening / unknown
            self._write(green=False, yellow=False, blue=False)

    def close(self) -> None:
        if not self._available:
            return
        self._cancel_blink()
        self._write(green=False, yellow=False, blue=False)
        self._lg.gpiochip_close(self._h)
        self._h = None

    def _write(self, green: bool, yellow: bool, blue: bool) -> None:
        lg, h = self._lg, self._h
        lg.gpio_write(h, GREEN,  int(green))
        lg.gpio_write(h, YELLOW, int(yellow))
        lg.gpio_write(h, BLUE,   int(blue))

    def _start_blink(self, pin: int, interval: float) -> None:
        self._stop_blink.clear()
        self._blink_thread = threading.Thread(
            target=self._blink_loop, args=(pin, interval), daemon=True
        )
        self._blink_thread.start()

    def _blink_loop(self, pin: int, interval: float) -> None:
        lg, h = self._lg, self._h
        while not self._stop_blink.wait(interval):
            lg.gpio_write(h, pin, 1)
            if self._stop_blink.wait(interval):
                break
            lg.gpio_write(h, pin, 0)
        lg.gpio_write(h, pin, 0)

    def _cancel_blink(self) -> None:
        self._stop_blink.set()
        if self._blink_thread and self._blink_thread.is_alive():
            self._blink_thread.join(timeout=0.5)
        self._blink_thread = None
