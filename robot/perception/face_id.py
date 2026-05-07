"""Offline face identification — enroll and recognise faces from JPEG frames.

Embeddings are 128-d float32 vectors stored in a tiny .npz file.
Identification is a single numpy distance computation — no tokens consumed,
no network call, runs in ~50 ms on Pi 4.

Requires:  pip install face_recognition
           (installs dlib; first build on Pi takes ~10 min)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# L2 distance threshold.  face_recognition docs suggest 0.6 is a good default;
# 0.50 is stricter — avoids false positives at the cost of more "unknown" results.
MATCH_THRESHOLD = 0.50


class FaceIdentifier:
    """Enrol known faces and identify them from raw JPEG bytes."""

    def __init__(self, data_dir: Path) -> None:
        self._emb_path = data_dir / "face_embeddings.npz"
        self._idx_path = data_dir / "face_index.json"
        data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> tuple[list[str], dict[str, str], np.ndarray | None]:
        """Return (ids, names_map, embeddings_matrix | None)."""
        if not self._idx_path.exists():
            return [], {}, None
        idx = json.loads(self._idx_path.read_text())
        ids: list[str] = idx.get("ids", [])
        names: dict[str, str] = idx.get("names", {})
        if not ids or not self._emb_path.exists():
            return ids, names, None
        data = np.load(self._emb_path)
        return ids, names, data["embeddings"]

    def _save(self, ids: list[str], names: dict[str, str], embeddings: np.ndarray) -> None:
        self._idx_path.write_text(json.dumps({"ids": ids, "names": names}, indent=2))
        np.savez(self._emb_path, embeddings=embeddings)

    def _jpeg_to_rgb(self, jpeg: bytes) -> np.ndarray:
        import cv2
        arr = np.frombuffer(jpeg, np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Could not decode JPEG")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def _encode(self, jpeg: bytes) -> np.ndarray | None:
        """Return the first face encoding found in the image, or None."""
        import face_recognition
        rgb = self._jpeg_to_rgb(jpeg)
        encodings = face_recognition.face_encodings(rgb)
        return encodings[0] if encodings else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enroll(self, display_name: str, jpeg: bytes) -> str | None:
        """Enrol a face.  Returns person_id on success, None if no face found."""
        encoding = self._encode(jpeg)
        if encoding is None:
            logger.warning("enroll('%s'): no face detected", display_name)
            return None

        person_id = display_name.lower().replace(" ", "_")
        ids, names, matrix = self._load()

        if person_id in ids:
            idx = ids.index(person_id)
            matrix[idx] = encoding
        else:
            ids.append(person_id)
            matrix = encoding[np.newaxis] if matrix is None else np.vstack([matrix, encoding])

        names[person_id] = display_name
        self._save(ids, names, matrix)
        logger.info("Enrolled face: '%s' → id='%s'", display_name, person_id)
        return person_id

    def identify(self, jpeg: bytes) -> str | None:
        """Identify the face in the image.  Returns person_id or None."""
        ids, _names, matrix = self._load()
        if not ids or matrix is None:
            return None

        encoding = self._encode(jpeg)
        if encoding is None:
            return None

        import face_recognition
        distances = face_recognition.face_distance(matrix, encoding)
        best = int(np.argmin(distances))
        if distances[best] <= MATCH_THRESHOLD:
            logger.info("Identified '%s' (dist=%.3f)", ids[best], distances[best])
            return ids[best]

        logger.debug("No match (best dist=%.3f > threshold %.2f)", distances[best], MATCH_THRESHOLD)
        return None

    def get_name(self, person_id: str) -> str:
        """Return the display name for a person_id, falling back to the id itself."""
        _ids, names, _matrix = self._load()
        return names.get(person_id, person_id)

    def known_people(self) -> dict[str, str]:
        """Return {person_id: display_name} for all enrolled faces."""
        _ids, names, _matrix = self._load()
        return dict(names)
