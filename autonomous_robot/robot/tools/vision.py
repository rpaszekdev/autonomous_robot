"""describe_scene() handler — captures a fresh camera frame and
pushes it into the Gemini Live session as additional visual context.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from robot import ui
from robot.perception.camera import Camera

logger = logging.getLogger(__name__)

ImageSender = Callable[[bytes], Awaitable[None]]


class VisionService:
    def __init__(self, camera: Camera, send_image: ImageSender) -> None:
        self._camera = camera
        self._send_image = send_image

    async def handle(self, args: dict) -> dict:
        focus = args.get("focus")
        try:
            jpeg = self._camera.capture_jpeg()
        except Exception as exc:
            logger.exception("camera capture failed")
            return {"error": f"camera capture failed: {exc}"}
        await self._send_image(jpeg)
        ui.camera_frame_sent(len(jpeg), source="describe_scene")
        return {
            "ok": True,
            "bytes": len(jpeg),
            "focus": focus,
            "note": "Fresh camera frame was sent as visual context.",
        }
