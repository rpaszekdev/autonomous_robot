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

from robot import config, ui
from robot.hardware import detect
from robot.hardware.gpio import MockGpio, rpi_gpio
from robot.hardware.motors import MockMotors, gpio_motors
from robot.perception.camera import MockCamera, OpenCVCamera, pi_camera, probe_webcams
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
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="List all available webcams (with index + resolution) and exit.",
    )
    return parser.parse_args()


def _list_cameras_and_exit() -> int:
    from robot import ui
    ui.install_logging()
    ui.console.print("[bold]Scanning webcams (indices 0–3)…[/]")
    cams = probe_webcams(max_index=4)
    if not cams:
        ui.error("No webcams found. On macOS, allow camera access in "
                 "System Settings → Privacy & Security → Camera, "
                 "then restart Terminal.")
        return 1
    for c in cams:
        ui.console.print(
            f"  [green]✓[/] index=[bold]{c['index']}[/]  "
            f"{c['width']}x{c['height']}  [dim]backend={c['backend']}[/]"
        )
    ui.console.print(
        f"\n[dim]Use:  python -m robot.main --simulate --webcam "
        f"--webcam-index <N>[/]"
    )
    return 0


def _setup_logging() -> None:
    ui.install_logging(level=logging.INFO)


async def _async_main(args: argparse.Namespace) -> int:
    cfg = config.load()
    simulate = detect.should_simulate(args.simulate or cfg.simulate_forced)

    webcam_detail = ""
    if args.webcam:
        cams = probe_webcams(max_index=max(args.webcam_index + 1, 4))
        match = next((c for c in cams if c["index"] == args.webcam_index), None)
        if match is None:
            ui.error(
                f"Webcam index {args.webcam_index} not available. "
                "Run `python -m robot.main --list-cameras` to see options."
            )
            return 1
        webcam_detail = f"index {match['index']} · {match['width']}x{match['height']}"
    ui.startup(model=cfg.gemini_model, simulate=simulate,
               webcam=args.webcam, webcam_detail=webcam_detail)

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()

    def _on_signal() -> None:
        ui.info("Shutdown signal received — closing cleanly")
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
    args = _parse_args()
    if args.list_cameras:
        return _list_cameras_and_exit()
    _setup_logging()
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
