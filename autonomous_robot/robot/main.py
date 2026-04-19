"""CLI entry point.

Examples:
    python -m robot.main              # auto-detect (Mac → simulate, Pi → real)
    python -m robot.main --simulate   # force mocks
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from robot import config
from robot.hardware import detect
from robot.hardware.gpio import MockGpio, rpi_gpio
from robot.hardware.motors import MockMotors, gpio_motors
from robot.perception.camera import MockCamera, OpenCVCamera, pi_camera
from robot.perception.wake import KeyboardWake, OpenWakeWordWake
from robot.runtime import Services, run
from robot.tools.gpio_signal import GpioService
from robot.tools.memory import MemoryStore
from robot.tools.motion import MotionService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gemini Live conversational robot")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Force mock hardware (camera, motors, GPIO). Auto-enabled off-Pi.",
    )
    parser.add_argument(
        "--webcam",
        action="store_true",
        help="Use the real Mac/Linux webcam via OpenCV instead of the mock camera.",
    )
    parser.add_argument(
        "--webcam-index",
        type=int,
        default=0,
        help="Webcam device index (default 0).",
    )
    parser.add_argument(
        "--wake-model",
        default=None,
        help="Path to openWakeWord .onnx model (Pi only).",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def _async_main(args: argparse.Namespace) -> int:
    cfg = config.load()
    simulate = detect.should_simulate(args.simulate or cfg.simulate_forced)

    logging.info(
        "Starting robot — simulate=%s, model=%s", simulate, cfg.gemini_model
    )

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()

    def _on_signal() -> None:
        logging.info("Shutdown signal received")
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _on_signal())

    # Wire services
    memory = MemoryStore(cfg.memory_path)
    if simulate:
        if args.webcam:
            camera = OpenCVCamera(index=args.webcam_index)
        else:
            camera = MockCamera()
        motors = MockMotors()
        gpio = MockGpio()
        wake = KeyboardWake(loop)
    else:
        camera = pi_camera()
        motors = gpio_motors(left_pins=(7, 8), right_pins=(9, 10))
        gpio = rpi_gpio()
        if args.wake_model is None:
            raise SystemExit(
                "Pi mode requires --wake-model <path to .onnx>"
            )
        wake = OpenWakeWordWake(loop, model_path=args.wake_model)

    services = Services(
        camera=camera,
        wake=wake,
        motion=MotionService(motors),
        gpio=GpioService(gpio),
        memory=memory,
    )

    try:
        await run(cfg, services, shutdown)
    finally:
        wake.stop()
        camera.close()
        gpio.close()
    return 0


def main() -> int:
    _setup_logging()
    args = _parse_args()
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
