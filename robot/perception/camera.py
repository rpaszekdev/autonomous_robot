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

    def __init__(
        self,
        source: int | str = 0,
        width: int = 640,
        height: int = 480,
    ) -> None:
        import cv2  # imported lazily — only when real camera is selected
        import time

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(source)
        if not self._cap.isOpened():
            hint = (
                "On macOS, check System Settings → Privacy & Security → Camera."
                if isinstance(source, int)
                else "Check the URL/credentials and network reachability."
            )
            raise RuntimeError(f"Could not open camera {source!r}. {hint}")
        if isinstance(source, int):
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._source_label = str(source)
        # Warm-up: discard frames until auto-exposure settles. The first
        # several reads on macOS are very dark; we want a non-black frame.
        start = time.time()
        last_mean = 0
        for _ in range(30):
            ok, frame = self._cap.read()
            if ok and frame is not None:
                last_mean = int(frame.mean())
                if last_mean > 40 or (time.time() - start) > 1.2:
                    break
            time.sleep(0.05)
        logger.info(
            "[camera] OpenCV ready (source=%s, brightness=%d)",
            self._source_label, last_mean,
        )

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


def probe_webcams(max_index: int = 4) -> list[dict]:
    """Return a list of available webcam indices with their properties.

    On macOS the first probe triggers the camera permission prompt.
    Silences cv2's stderr noise during probing.
    """
    import contextlib
    import os
    import sys

    import cv2

    results: list[dict] = []
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved_stderr = os.dup(2)
    try:
        os.dup2(devnull, 2)
        for idx in range(max_index):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                backend = cap.getBackendName()
                results.append({"index": idx, "width": w, "height": h, "backend": backend})
            cap.release()
    finally:
        os.dup2(saved_stderr, 2)
        os.close(devnull)
        os.close(saved_stderr)
    return results


def pi_camera(width: int = 1280, height: int = 720) -> Camera:
    """Open the Pi Camera Module (IMX219) for continuous capture.

    Key improvements over the original:
    - create_preview_configuration: designed for continuous capture; AE/AWB
      converge in the background, unlike still_configuration.
    - 1280x720 default: enough detail for Gemini to describe scenes clearly.
    - Sharpness boosted to 2.0 (default 1.0): IMX219 benefits significantly.
    - 2-second warmup: AE and AWB need time to settle from a cold start;
      without it the first frames are dark or colour-shifted.
    - PIL re-encode at quality=92: full control over JPEG quality instead of
      relying on picamera2's internal default (~85).
    """
    from picamera2 import Picamera2  # imported lazily — Pi only
    import time

    class PiCamera:
        def __init__(self) -> None:
            self._cam = Picamera2()
            # Preview config is designed for continuous capture. It runs
            # AE/AWB in the background while the stream is live, unlike
            # still_configuration which re-runs them per capture.
            config = self._cam.create_preview_configuration(
                main={"size": (width, height), "format": "RGB888"},
            )
            self._cam.configure(config)
            # IMX219 sharpness: 0=off, 1.0=default, 16.0=max.
            # 2.0 noticeably improves edge definition without artefacts.
            self._cam.set_controls({"Sharpness": 2.0})
            self._cam.start()
            # Let AE and AWB converge. Without this the first captured frame
            # is typically underexposed and colour-shifted.
            time.sleep(2.0)
            logger.info(
                "[pi camera] ready (%dx%d, warmed up, sharpness=2.0)", width, height
            )

        def capture_jpeg(self) -> bytes:
            from PIL import Image

            # capture_array() returns an RGB888 numpy array from the live
            # preview stream — no mode-switch latency, always settled AE/AWB.
            frame = self._cam.capture_array()
            img = Image.fromarray(frame)
            buf = io.BytesIO()
            # quality=92 gives excellent detail with ~2-3× less data than lossless.
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()

        def close(self) -> None:
            try:
                self._cam.stop()
            except Exception:
                pass

    return PiCamera()
