"""MAX7219 8x8 LED matrix abstraction.

Real hardware uses luma.led_matrix over SPI.
MockMatrix logs to console for Mac development.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Matrix(Protocol):
    def draw_grid(self, pixels: list[list[int]]) -> None: ...
    def draw_text(self, text: str, scroll: bool = False) -> None: ...
    def clear(self) -> None: ...
    def set_brightness(self, level: int) -> None: ...
    def close(self) -> None: ...


class MockMatrix:
    def draw_grid(self, pixels: list[list[int]]) -> None:
        lines = []
        for row in pixels[:8]:
            padded = (row + [0] * 8)[:8]
            lines.append("".join("█" if p else "·" for p in padded))
        logger.info("[SIM matrix]\n%s", "\n".join(lines))

    def draw_text(self, text: str, scroll: bool = False) -> None:
        action = "scroll" if scroll else "show"
        logger.info("[SIM matrix] %s: %s", action, text)

    def clear(self) -> None:
        logger.info("[SIM matrix] cleared")

    def set_brightness(self, level: int) -> None:
        logger.info("[SIM matrix] brightness=%d", level)

    def close(self) -> None:
        pass


def max7219_matrix(cascaded: int = 1, block_orientation: int = 90) -> Matrix:
    """Create a real MAX7219 matrix. Pi only — requires luma.led_matrix + SPI enabled."""
    from luma.core.interface.serial import spi, noop
    from luma.core.render import canvas
    from luma.led_matrix.device import max7219 as max7219_device
    from PIL import ImageFont
    import threading
    import time

    serial = spi(port=0, device=0, gpio=noop())
    device = max7219_device(
        serial,
        cascaded=cascaded,
        block_orientation=block_orientation,
        rotate=0,
    )
    device.contrast(128)

    class RealMatrix:
        def __init__(self) -> None:
            self._device = device
            self._scroll_stop = threading.Event()
            self._scroll_thread: threading.Thread | None = None

        def _stop_scroll(self) -> None:
            self._scroll_stop.set()
            if self._scroll_thread is not None and self._scroll_thread.is_alive():
                self._scroll_thread.join(timeout=2.0)
            self._scroll_stop.clear()
            self._scroll_thread = None

        def draw_grid(self, pixels: list[list[int]]) -> None:
            self._stop_scroll()
            with canvas(self._device) as draw:
                for y, row in enumerate(pixels[:8]):
                    for x, val in enumerate((row + [0] * 8)[:8]):
                        if val:
                            draw.point((x, y), fill="white")

        def draw_text(self, text: str, scroll: bool = False) -> None:
            self._stop_scroll()
            if not scroll:
                with canvas(self._device) as draw:
                    draw.text((0, 0), text[:2], fill="white")
                return

            def _scroll_worker() -> None:
                try:
                    font = ImageFont.load_default()
                    text_width = len(text) * 6 + self._device.width
                    for offset in range(text_width):
                        if self._scroll_stop.is_set():
                            return
                        with canvas(self._device) as draw:
                            draw.text((-offset, 0), text, fill="white", font=font)
                        time.sleep(0.05)
                except Exception:
                    logger.exception("Scroll thread error")

            self._scroll_thread = threading.Thread(target=_scroll_worker, daemon=True)
            self._scroll_thread.start()

        def clear(self) -> None:
            self._stop_scroll()
            with canvas(self._device) as draw:
                draw.rectangle(self._device.bounding_box, outline="black", fill="black")

        def set_brightness(self, level: int) -> None:
            clamped = max(0, min(255, level))
            self._device.contrast(clamped)

        def close(self) -> None:
            self._stop_scroll()
            self.clear()
            self._device.cleanup()

    return RealMatrix()
