"""GPIO pin abstraction for LEDs, relays, servos.

- RPiGpio (Pi): gpiozero.DigitalOutputDevice
- MockGpio (Mac): log commands only
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Gpio(Protocol):
    def set(self, pin: int, state: bool) -> None: ...
    def close(self) -> None: ...


class MockGpio:
    def set(self, pin: int, state: bool) -> None:
        logger.info("[SIM gpio] pin=%d %s", pin, "HIGH" if state else "LOW")

    def close(self) -> None:
        pass


def rpi_gpio() -> Gpio:
    from gpiozero import DigitalOutputDevice  # imported lazily — Pi only

    class RPiGpio:
        def __init__(self) -> None:
            self._pins: dict[int, DigitalOutputDevice] = {}

        def _pin(self, pin: int) -> DigitalOutputDevice:
            if pin not in self._pins:
                self._pins[pin] = DigitalOutputDevice(pin)
            return self._pins[pin]

        def set(self, pin: int, state: bool) -> None:
            device = self._pin(pin)
            if state:
                device.on()
            else:
                device.off()

        def close(self) -> None:
            for device in self._pins.values():
                device.close()
            self._pins.clear()

    return RPiGpio()
