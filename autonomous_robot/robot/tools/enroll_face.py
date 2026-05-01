"""enroll_face() handler — snapshot the camera and save the face embedding."""

from __future__ import annotations

import logging

from robot.perception.camera import Camera
from robot.perception.face_id import FaceIdentifier

logger = logging.getLogger(__name__)


class EnrollFaceService:
    def __init__(self, camera: Camera, face_id: FaceIdentifier) -> None:
        self._camera = camera
        self._face_id = face_id

    async def handle(self, args: dict) -> dict:
        name = str(args.get("name", "")).strip()
        if not name:
            return {"error": "name is required"}

        try:
            jpeg = self._camera.capture_jpeg()
        except Exception as exc:
            logger.exception("Camera capture failed during enroll_face")
            return {"error": f"camera failed: {exc}"}

        person_id = self._face_id.enroll(name, jpeg)
        if person_id is None:
            return {
                "error": (
                    "No face detected in frame. "
                    "Make sure your face is clearly visible to the camera and try again."
                )
            }

        return {"ok": True, "enrolled_as": name, "person_id": person_id}
