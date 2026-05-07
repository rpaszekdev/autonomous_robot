"""Motor abstraction: differential-drive wheels.

- GpioMotors (Pi): gpiozero.Robot
- MockMotors (Mac): log commands only
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Motors(Protocol):
    def forward(self, speed: float) -> None: ...
    def backward(self, speed: float) -> None: ...
    def left(self, speed: float) -> None: ...
    def right(self, speed: float) -> None: ...
    def stop(self) -> None: ...


class MockMotors:
    def forward(self, speed: float) -> None:
        logger.info("[SIM motors] FORWARD speed=%.2f", speed)

    def backward(self, speed: float) -> None:
        logger.info("[SIM motors] BACKWARD speed=%.2f", speed)

    def left(self, speed: float) -> None:
        logger.info("[SIM motors] LEFT speed=%.2f", speed)

    def right(self, speed: float) -> None:
        logger.info("[SIM motors] RIGHT speed=%.2f", speed)

    def stop(self) -> None:
        logger.info("[SIM motors] STOP")


def gpio_motors(left_pins: tuple[int, int], right_pins: tuple[int, int]) -> Motors:
    from gpiozero import Robot  # imported lazily — Pi only

    robot = Robot(left=left_pins, right=right_pins)

    class GpioMotors:
        def forward(self, speed: float) -> None:
            robot.forward(speed)

        def backward(self, speed: float) -> None:
            robot.backward(speed)

        def left(self, speed: float) -> None:
            robot.left(speed)

        def right(self, speed: float) -> None:
            robot.right(speed)

        def stop(self) -> None:
            robot.stop()

    return GpioMotors()
