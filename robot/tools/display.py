"""set_display() tool — Gemini-controlled 8x8 LED matrix.

Gives Gemini a tiny screen to draw emoji, text, patterns, or anything
it can imagine on an 8x8 pixel grid.

Talking animation: when Gemini speaks, the current face automatically
animates a mouth-open/mouth-closed cycle. Gemini sets the emotion
first, the runtime triggers the animation via on_state_change.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

# Each face has a "closed" (default) and "open" (talking) variant.
# The open variant modifies rows 5-6 to show an open mouth.

FACES: dict[str, dict[str, list[list[int]]]] = {
    "happy": {
        "closed": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
        "open": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [0, 1, 0, 1, 1, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
    },
    "sad": {
        "closed": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
        "open": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [0, 1, 0, 1, 1, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
    },
    "neutral": {
        "closed": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 1, 1, 1, 1, 0, 1],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
        "open": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [0, 1, 0, 1, 1, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
    },
    "angry": {
        "closed": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 1, 0, 0, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 1, 1, 1, 1, 0, 1],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
        "open": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [1, 1, 0, 0, 0, 0, 1, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [0, 1, 0, 1, 1, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
    },
    "surprised": {
        "closed": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 1, 1, 0, 0, 1, 1, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [1, 0, 0, 1, 1, 0, 0, 1],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
        "open": [
            [0, 0, 1, 1, 1, 1, 0, 0],
            [0, 1, 0, 0, 0, 0, 1, 0],
            [1, 1, 1, 0, 0, 1, 1, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 1, 1, 1, 1, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1],
            [0, 1, 0, 1, 1, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 0, 0],
        ],
    },
}

# Non-face icons (no talking animation)
BUILTIN_ICONS: dict[str, list[list[int]]] = {
    "heart": [
        [0, 1, 1, 0, 0, 1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [0, 1, 1, 1, 1, 1, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 0, 0, 1, 1, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    "check": [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0, 0, 0],
        [1, 0, 0, 1, 0, 0, 0, 0],
        [0, 1, 1, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    "x": [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [0, 0, 1, 0, 0, 1, 0, 0],
        [0, 0, 0, 1, 1, 0, 0, 0],
        [0, 0, 0, 1, 1, 0, 0, 0],
        [0, 0, 1, 0, 0, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    "question": [
        [0, 0, 1, 1, 1, 0, 0, 0],
        [0, 1, 0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
    ],
    "arrow_up": [
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 1, 1, 1, 0, 0, 0],
        [0, 1, 0, 1, 0, 1, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    "skull": [
        [0, 1, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 1, 1, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [0, 1, 1, 1, 1, 1, 1, 0],
        [0, 1, 0, 1, 1, 0, 1, 0],
        [0, 0, 1, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
}

TALK_INTERVAL = 0.2


class MatrixDevice(Protocol):
    def draw_grid(self, pixels: list[list[int]]) -> None: ...
    def draw_text(self, text: str, scroll: bool = False) -> None: ...
    def clear(self) -> None: ...
    def set_brightness(self, level: int) -> None: ...


class DisplayToolService:
    def __init__(self, matrix: MatrixDevice) -> None:
        self._matrix = matrix
        self._animation_task: asyncio.Task | None = None
        self._talk_task: asyncio.Task | None = None
        self._current_face: str | None = None
        self._current_custom: list[list[int]] | None = None

    def _cancel_animation(self) -> None:
        if self._animation_task is not None and not self._animation_task.done():
            self._animation_task.cancel()
            self._animation_task = None

    def _cancel_talk(self) -> None:
        if self._talk_task is not None and not self._talk_task.done():
            self._talk_task.cancel()
            self._talk_task = None

    def start_talking(self) -> None:
        self._cancel_talk()
        self._cancel_animation()
        face_name = self._current_face or "neutral"
        face = FACES.get(face_name)
        if face is None:
            face = FACES["neutral"]

        closed_frame = face["closed"]
        open_frame = face["open"]

        async def _talk_loop() -> None:
            try:
                mouth_open = False
                while True:
                    frame = open_frame if mouth_open else closed_frame
                    self._matrix.draw_grid(frame)
                    mouth_open = not mouth_open
                    await asyncio.sleep(TALK_INTERVAL)
            except asyncio.CancelledError:
                pass

        self._talk_task = asyncio.get_event_loop().create_task(_talk_loop())

    def stop_talking(self) -> None:
        self._cancel_talk()
        if self._current_face and self._current_face in FACES:
            self._matrix.draw_grid(FACES[self._current_face]["closed"])
        elif self._current_custom:
            self._matrix.draw_grid(self._current_custom)

    def on_state_change(self, state: str) -> None:
        if state == "gemini_speaking":
            self.start_talking()
        elif state == "listening":
            self.stop_talking()
        elif state.startswith("tool:"):
            self._cancel_talk()
        elif state == "idle":
            self._cancel_talk()
            self._cancel_animation()

    async def handle(self, args: dict) -> dict:
        self._cancel_animation()
        self._cancel_talk()

        face = args.get("face")
        icon = args.get("icon")
        pixels = args.get("pixels")
        text = args.get("text")
        scroll = args.get("scroll", False)
        animation = args.get("animation")
        brightness = args.get("brightness")
        clear = args.get("clear", False)

        if brightness is not None:
            self._matrix.set_brightness(int(brightness))

        if clear:
            self._current_face = None
            self._current_custom = None
            self._matrix.clear()
            return {"ok": True, "action": "cleared"}

        if face is not None:
            face_data = FACES.get(face)
            if face_data is None:
                available = list(FACES.keys())
                return {"error": f"Unknown face '{face}'. Available: {available}"}
            self._current_face = face
            self._current_custom = None
            self._matrix.draw_grid(face_data["closed"])
            return {"ok": True, "action": "face", "face": face}

        if icon is not None:
            grid = BUILTIN_ICONS.get(icon)
            if grid is None:
                available = list(BUILTIN_ICONS.keys()) + list(FACES.keys())
                return {"error": f"Unknown icon '{icon}'. Available: {available}"}
            self._current_face = None
            self._current_custom = grid
            self._matrix.draw_grid(grid)
            return {"ok": True, "action": "icon", "icon": icon}

        if pixels is not None:
            if not isinstance(pixels, list):
                return {"error": "'pixels' must be 8 rows of 8 values (0 or 1)."}
            grid = _normalize_grid(pixels)
            self._current_face = None
            self._current_custom = grid
            self._matrix.draw_grid(grid)
            return {"ok": True, "action": "pixels"}

        if text is not None:
            self._current_face = None
            self._current_custom = None
            self._matrix.draw_text(str(text), scroll=bool(scroll))
            action = "scroll_text" if scroll else "static_text"
            return {"ok": True, "action": action, "text": str(text)}

        if animation is not None:
            return await self._run_animation(animation)

        return {"error": "Provide one of: face, icon, pixels, text, animation, or clear."}

    async def _run_animation(self, frames: list) -> dict:
        if not isinstance(frames, list) or len(frames) == 0:
            return {"error": "'animation' must be a non-empty list of frames."}
        if len(frames) > 30:
            return {"error": "Animation too long (max 30 frames)."}

        async def _play() -> None:
            for frame in frames:
                if not isinstance(frame, dict):
                    continue
                duration_ms = frame.get("duration_ms", 300)

                face_name = frame.get("face")
                icon_name = frame.get("icon")
                if face_name and face_name in FACES:
                    self._matrix.draw_grid(FACES[face_name]["closed"])
                    self._current_face = face_name
                elif icon_name and icon_name in BUILTIN_ICONS:
                    self._matrix.draw_grid(BUILTIN_ICONS[icon_name])
                elif "pixels" in frame:
                    self._matrix.draw_grid(_normalize_grid(frame["pixels"]))

                await asyncio.sleep(max(50, min(5000, int(duration_ms))) / 1000.0)

        self._animation_task = asyncio.create_task(_play())
        return {"ok": True, "action": "animation", "frames": len(frames)}

    def close(self) -> None:
        self._cancel_talk()
        self._cancel_animation()
        self._matrix.clear()


def _normalize_grid(pixels: list) -> list[list[int]]:
    grid = []
    for row in pixels[:8]:
        if isinstance(row, list):
            grid.append([int(bool(v)) for v in (row + [0] * 8)[:8]])
        else:
            grid.append([0] * 8)
    while len(grid) < 8:
        grid.append([0] * 8)
    return grid
