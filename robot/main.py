"""CLI entry point.

Examples:
    python -m robot.main              # auto-detect (Mac → simulate, Pi → real)
    python -m robot.main --simulate   # force mocks
    python -m robot.main --network-audio  # mic from Mac over TCP
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
from robot.hardware.leds import LedController
from robot.perception.face_id import FaceIdentifier
from robot.perception.wake import KeyboardWake, OpenWakeWordWake
from robot.runtime import Services, run
from robot.tools.gpio_signal import GpioService
from robot.tools.leds import LedToolService
from robot.tools.display import DisplayToolService
from robot.hardware.matrix import MockMatrix, max7219_matrix
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
        default=None,
        help="Use the real local webcam via OpenCV (default on Mac/Linux).",
    )
    parser.add_argument(
        "--mock-camera",
        dest="mock_camera",
        action="store_true",
        help="Force the mock test-image camera instead of your real webcam.",
    )
    parser.add_argument(
        "--webcam-index",
        type=int,
        default=0,
        help="Webcam device index (default 0).",
    )
    parser.add_argument(
        "--camera-url",
        default=None,
        help=(
            "Open an IP camera stream instead of a local webcam. "
            "Accepts RTSP, HTTP-MJPEG, or any URL OpenCV can decode. "
            "Examples: rtsp://user:pass@192.168.1.50:554/stream1 · "
            "http://192.168.1.50:8080/video"
        ),
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
    parser.add_argument(
        "--network-audio",
        type=int,
        nargs="?",
        const=9999,
        metavar="PORT",
        help="Receive mic audio over TCP from Mac (default port 9999).",
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

    # Camera resolution:
    #  1) --mock-camera → force mock
    #  2) --camera-url → IP stream
    #  3) --webcam or auto-detect on simulate Mac/Linux → real webcam
    #  4) fallback → mock
    webcam_detail = ""
    use_real_camera = False
    if args.mock_camera:
        pass  # explicit mock
    elif args.camera_url:
        use_real_camera = True
        webcam_detail = f"IP stream: {args.camera_url}"
    else:
        # Auto-enable webcam in simulate mode unless --webcam is explicitly False.
        want_webcam = args.webcam if args.webcam is not None else simulate
        if want_webcam:
            cams = probe_webcams(max_index=max(args.webcam_index + 1, 4))
            match = next((c for c in cams if c["index"] == args.webcam_index), None)
            if match is None:
                ui.error(
                    f"Webcam index {args.webcam_index} not available. "
                    "Run `python -m robot.main --list-cameras` to see options, "
                    "or pass --mock-camera to use the test image."
                )
                return 1
            use_real_camera = True
            webcam_detail = f"index {match['index']} · {match['width']}x{match['height']}"
    ui.startup(model=cfg.gemini_model, simulate=simulate,
               webcam=use_real_camera, webcam_detail=webcam_detail)
    if not use_real_camera:
        ui.console.print(
            "  [yellow]⚠  Using MOCK CAMERA — Gemini will see a blue test image, "
            "not your real world.[/]\n"
            "  [dim]Drop --mock-camera (or add --webcam / --camera-url) "
            "for real video.[/]"
        )

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
    face_id = FaceIdentifier(cfg.memory_path.parent / "faces")
    leds = LedController()
    if simulate:
        if use_real_camera and args.camera_url:
            camera = OpenCVCamera(source=args.camera_url)
        elif use_real_camera:
            camera = OpenCVCamera(source=args.webcam_index)
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
            wake = KeyboardWake(loop)
        else:
            wake = OpenWakeWordWake(loop, model_path=args.wake_model)

    led_tool = LedToolService(gpio)
    if simulate:
        matrix = MockMatrix()
    else:
        try:
            matrix = max7219_matrix()
        except Exception as exc:
            ui.info(f"MAX7219 not available ({exc}) — using mock display")
            matrix = MockMatrix()
    display_tool = DisplayToolService(matrix)
    services = Services(
        camera=camera,
        wake=wake,
        motion=MotionService(motors),
        gpio=GpioService(gpio),
        memory=memory,
        face_id=face_id,
        leds=leds,
        led_tool=led_tool,
        display=display_tool,
    )

    try:
        await run(cfg, services, shutdown, network_audio_port=args.network_audio)
    finally:
        wake.stop()
        camera.close()
        display_tool.close()
        matrix.close()
        gpio.close()
        leds.close()
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
