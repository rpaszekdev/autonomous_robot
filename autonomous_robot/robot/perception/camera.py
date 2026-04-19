"""Camera source: real Pi Camera or mock test image."""

from __future__ import annotations

import io
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Camera(Protocol):
    def capture_jpeg(self) -> bytes: ...
    def close(self) -> None: ...


class MockCamera:
    """Generates a colored test JPEG — lets describe_scene remain meaningful."""

    def __init__(self, width: int = 640, height: int = 480) -> None:
        self._size = (width, height)
        self._counter = 0
        logger.info("[SIM camera] ready (%dx%d test frames)", width, height)

    def capture_jpeg(self) -> bytes:
        from PIL import Image, ImageDraw

        self._counter += 1
        hue = (self._counter * 47) % 256
        image = Image.new("RGB", self._size, color=(hue, 120, 200))
        draw = ImageDraw.Draw(image)
        draw.text((20, 20), f"MOCK FRAME {self._counter}", fill=(255, 255, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=80)
        return buffer.getvalue()

    def close(self) -> None:
        pass


class OpenCVCamera:
    """Real webcam via OpenCV — works on macOS and Linux.

    Uses cv2.VideoCapture(index). On macOS the first read triggers a camera
    permission prompt. Returns JPEG bytes matching the same contract as
    MockCamera / PiCamera.
    """

    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        import cv2  # imported lazily — only when real webcam is selected

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open webcam index {index}. On macOS, check "
                "System Settings → Privacy & Security → Camera."
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        # Discard warm-up frames (first ones are often black/dim)
        for _ in range(5):
            self._cap.read()
        logger.info("[webcam] OpenCV camera ready (index=%d)", index)

    def capture_jpeg(self) -> bytes:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("webcam read failed")
        ok, buffer = self._cv2.imencode(".jpg", frame, [self._cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise RuntimeError("JPEG encode failed")
        return bytes(buffer)

    def close(self) -> None:
        try:
            self._cap.release()
        except Exception:
            pass


def pi_camera(width: int = 640, height: int = 480) -> Camera:
    from picamera2 import Picamera2  # imported lazily — Pi only

    class PiCamera:
        def __init__(self) -> None:
            self._cam = Picamera2()
            config = self._cam.create_still_configuration(
                main={"size": (width, height), "format": "RGB888"}
            )
            self._cam.configure(config)
            self._cam.start()

        def capture_jpeg(self) -> bytes:
            buffer = io.BytesIO()
            self._cam.capture_file(buffer, format="jpeg")
            return buffer.getvalue()

        def close(self) -> None:
            try:
                self._cam.stop()
            except Exception:
                pass

    return PiCamera()
