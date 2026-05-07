"""describe_scene() handler — captures a fresh camera frame and
pushes it into the Gemini Live session as additional visual context.
"""

from __future__ import annotations

import asyncio
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
        # Give the camera's AE/AWB ~300 ms to re-settle for the current scene
        # before capturing. On-demand captures happen after the mic goes silent
        # and Gemini has started talking — lighting may have changed.
        await asyncio.sleep(0.3)
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
