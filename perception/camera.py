"""Pi Camera Module 3 snapshot capture.

Takes a JPEG snapshot for vision input to Gemma 4.
Runs in parallel with audio recording.
"""

import io
import logging
import base64

logger = logging.getLogger(__name__)

RESOLUTION = (640, 480)


class Camera:
    def __init__(self):
        self._camera = None

    def _ensure_camera(self):
        if self._camera is None:
            from picamera2 import Picamera2
            self._camera = Picamera2()
            config = self._camera.create_still_configuration(
                main={"size": RESOLUTION, "format": "RGB888"}
            )
            self._camera.configure(config)
            self._camera.start()
            logger.info("Camera initialised at %s", RESOLUTION)

    def capture_jpeg(self) -> bytes:
        """Capture a single JPEG frame.

        Returns:
            JPEG-encoded image bytes.
        """
        self._ensure_camera()
        stream = io.BytesIO()
        self._camera.capture_file(stream, format="jpeg")
        jpeg_bytes = stream.getvalue()
        logger.info("Captured JPEG snapshot (%d bytes)", len(jpeg_bytes))
        return jpeg_bytes

    def capture_base64(self) -> str:
        """Capture a JPEG frame and return as base64 string."""
        return base64.b64encode(self.capture_jpeg()).decode("ascii")

    def close(self):
        if self._camera:
            self._camera.stop()
            self._camera.close()
            self._camera = None
