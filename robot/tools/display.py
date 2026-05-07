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

FACES["excited"] = {
    "closed": [
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [1, 1, 1, 0, 0, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [1, 0, 0, 1, 1, 0, 0, 1],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ],
    "open": [
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [1, 1, 1, 0, 0, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 0, 1, 1, 0, 0, 1],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [0, 1, 0, 1, 1, 0, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ],
}

FACES["sleepy"] = {
    "closed": [
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 1, 0, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 1, 1, 1, 0, 1],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ],
    "open": [
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 1, 0, 1, 1, 1],
        [1, 0, 0, 1, 1, 0, 0, 1],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [0, 1, 0, 1, 1, 0, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ],
}

FACES["wink"] = {
    "closed": [
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [1, 0, 0, 0, 0, 1, 0, 1],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [1, 0, 0, 1, 1, 0, 0, 1],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ],
    "open": [
        [0, 0, 1, 1, 1, 1, 0, 0],
        [0, 1, 0, 0, 0, 0, 1, 0],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [1, 0, 0, 0, 0, 1, 0, 1],
        [1, 0, 0, 1, 1, 0, 0, 1],
        [1, 0, 1, 0, 0, 1, 0, 1],
        [0, 1, 0, 1, 1, 0, 1, 0],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ],
}

# Built-in animations Gemini can trigger by name
BUILTIN_ANIMATIONS: dict[str, list[dict]] = {
    "wave": [
        {"pixels": [
            [0,0,0,0,1,1,0,0],
            [0,0,0,1,0,0,1,0],
            [0,0,0,1,0,0,1,0],
            [0,0,0,0,1,1,0,0],
            [0,0,0,0,1,0,0,0],
            [0,0,0,1,1,1,0,0],
            [0,0,1,0,1,0,0,0],
            [0,0,0,0,1,0,0,0],
        ], "duration_ms": 300},
        {"pixels": [
            [0,0,1,1,0,0,0,0],
            [0,1,0,0,1,0,0,0],
            [0,1,0,0,1,0,0,0],
            [0,0,1,1,0,0,0,0],
            [0,0,0,1,0,0,0,0],
            [0,0,1,1,1,0,0,0],
            [0,0,1,0,1,0,0,0],
            [0,0,0,0,1,0,0,0],
        ], "duration_ms": 300},
        {"pixels": [
            [1,1,0,0,0,0,0,0],
            [0,0,1,0,0,0,0,0],
            [0,0,1,0,0,0,0,0],
            [1,1,0,0,0,0,0,0],
            [0,0,0,1,0,0,0,0],
            [0,0,1,1,1,0,0,0],
            [0,0,1,0,1,0,0,0],
            [0,0,0,0,1,0,0,0],
        ], "duration_ms": 300},
        {"pixels": [
            [0,0,1,1,0,0,0,0],
            [0,1,0,0,1,0,0,0],
            [0,1,0,0,1,0,0,0],
            [0,0,1,1,0,0,0,0],
            [0,0,0,1,0,0,0,0],
            [0,0,1,1,1,0,0,0],
            [0,0,1,0,1,0,0,0],
            [0,0,0,0,1,0,0,0],
        ], "duration_ms": 300},
        {"pixels": [
            [0,0,0,0,1,1,0,0],
            [0,0,0,1,0,0,1,0],
            [0,0,0,1,0,0,1,0],
            [0,0,0,0,1,1,0,0],
            [0,0,0,0,1,0,0,0],
            [0,0,0,1,1,1,0,0],
            [0,0,1,0,1,0,0,0],
            [0,0,0,0,1,0,0,0],
        ], "duration_ms": 300},
    ],
    "heartbeat": [
        {"icon": "heart", "duration_ms": 200},
        {"pixels": [[0]*8 for _ in range(8)], "duration_ms": 150},
        {"icon": "heart", "duration_ms": 200},
        {"pixels": [[0]*8 for _ in range(8)], "duration_ms": 400},
        {"icon": "heart", "duration_ms": 200},
        {"pixels": [[0]*8 for _ in range(8)], "duration_ms": 150},
        {"icon": "heart", "duration_ms": 200},
        {"pixels": [[0]*8 for _ in range(8)], "duration_ms": 400},
    ],
    "sparkle": [
        {"pixels": [
            [1,0,0,0,0,0,0,1],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [1,0,0,0,0,0,0,1],
        ], "duration_ms": 150},
        {"pixels": [
            [0,0,0,0,0,0,0,0],
            [0,1,0,0,0,0,1,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,1,1,0,0,0],
            [0,0,0,1,1,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,1,0,0,0,0,1,0],
            [0,0,0,0,0,0,0,0],
        ], "duration_ms": 150},
        {"pixels": [
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
        ], "duration_ms": 150},
        {"pixels": [
            [0,0,0,1,1,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [1,0,0,0,0,0,0,1],
            [1,0,0,0,0,0,0,1],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,1,1,0,0,0],
        ], "duration_ms": 150},
        {"pixels": [
            [1,0,0,0,0,0,0,1],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [1,0,0,0,0,0,0,1],
        ], "duration_ms": 150},
    ],
}

TALK_INTERVAL = 0.2

# Tic-tac-toe on 8x8 grid.
# No grid lines — cells are separated by empty gaps.
# Each cell is 2x2 pixels. Gap columns: 2, 5. Gap rows: 2, 5.
#
# X = filled 2x2 block  ██
#                        ██
#
# O = ring/dot pattern   ██
#                        ·· (only top row lit — dash shape)
#
# Actually, to make them VERY distinct:
# X = both diagonals (cross shape across the 2x2)
# O = top+bottom rows only (horizontal lines)
#
# Simplest approach that works: X = ALL 4 pixels on, O = only 2 pixels on
# X: ██    O: ·█
#    ██       █·

_CELL_ORIGINS = [
    (0, 0), (0, 3), (0, 6),
    (3, 0), (3, 3), (3, 6),
    (6, 0), (6, 3), (6, 6),
]


def _render_tictactoe(board: str) -> list[list[int]]:
    grid = [[0] * 8 for _ in range(8)]

    # No grid lines — the 1px gap between cells is the visual separator.
    # X = diagonal (2 LEDs), O = solid block (4 LEDs). Clearly distinct.
    for idx, ch in enumerate(board[:9]):
        upper = ch.upper()
        if upper not in ("X", "O"):
            continue
        r, c = _CELL_ORIGINS[idx]
        if upper == "X":
            grid[r][c] = 1
            grid[r + 1][c + 1] = 1
        else:
            grid[r][c] = 1
            grid[r][c + 1] = 1
            grid[r + 1][c] = 1
            grid[r + 1][c + 1] = 1

    return grid


_WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


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
        self._pinned = False  # True = display is locked (tictactoe, icon, pixels, text)

    def _cancel_animation(self) -> None:
        if self._animation_task is not None and not self._animation_task.done():
            self._animation_task.cancel()
            self._animation_task = None

    def _cancel_talk(self) -> None:
        if self._talk_task is not None and not self._talk_task.done():
            self._talk_task.cancel()
            self._talk_task = None

    def start_talking(self) -> None:
        if self._pinned:
            return  # tictactoe/icon/pixels on screen — don't override
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
        if self._pinned:
            return  # keep pinned content (tictactoe, icon, etc.)
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

    def show_tictactoe(self, board: str) -> dict:
        return self._handle_tictactoe(board)

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
            self._pinned = False
            self._matrix.clear()
            return {"ok": True, "action": "cleared"}

        if face is not None:
            face_data = FACES.get(face)
            if face_data is None:
                available = list(FACES.keys())
                return {"error": f"Unknown face '{face}'. Available: {available}"}
            self._current_face = face
            self._current_custom = None
            self._pinned = False  # faces animate when speaking
            self._matrix.draw_grid(face_data["closed"])
            return {"ok": True, "action": "face", "face": face}

        if icon is not None:
            grid = BUILTIN_ICONS.get(icon)
            if grid is None:
                available = list(BUILTIN_ICONS.keys()) + list(FACES.keys())
                return {"error": f"Unknown icon '{icon}'. Available: {available}"}
            self._current_face = None
            self._current_custom = grid
            self._pinned = True  # stay on screen
            self._matrix.draw_grid(grid)
            return {"ok": True, "action": "icon", "icon": icon}

        if pixels is not None:
            if not isinstance(pixels, list):
                return {"error": "'pixels' must be 8 rows of 8 values (0 or 1)."}
            grid = _normalize_grid(pixels)
            self._current_face = None
            self._current_custom = grid
            self._pinned = True  # stay on screen
            self._matrix.draw_grid(grid)
            return {"ok": True, "action": "pixels"}

        if text is not None:
            self._current_face = None
            self._current_custom = None
            self._pinned = True  # stay on screen
            self._matrix.draw_text(str(text), scroll=bool(scroll))
            action = "scroll_text" if scroll else "static_text"
            return {"ok": True, "action": action, "text": str(text)}

        tictactoe = args.get("tictactoe")
        if tictactoe is not None:
            return self._handle_tictactoe(tictactoe)

        play_animation = args.get("play_animation")
        if play_animation is not None:
            anim_name = str(play_animation).lower()
            builtin = BUILTIN_ANIMATIONS.get(anim_name)
            if builtin is None:
                available = list(BUILTIN_ANIMATIONS.keys())
                return {"error": f"Unknown animation '{anim_name}'. Available: {available}"}
            self._pinned = True
            return await self._run_animation(builtin)

        if animation is not None:
            self._pinned = True
            return await self._run_animation(animation)

        return {"error": "Provide one of: face, icon, pixels, text, animation, or clear."}

    def _handle_tictactoe(self, board: str) -> dict:
        board = str(board).replace(" ", "").replace(",", "").replace("|", "")
        if len(board) != 9:
            return {
                "error": "tictactoe must be 9 characters: X, O, or _ for empty. "
                "Example: 'X_O__X__O' (positions 1-9, left-to-right, top-to-bottom)"
            }
        for ch in board:
            if ch not in ("X", "O", "x", "o", "_", "-", "."):
                return {"error": f"Invalid character '{ch}'. Use X, O, or _ for empty."}

        grid = _render_tictactoe(board)
        self._current_face = None
        self._current_custom = grid
        self._pinned = True  # board stays on screen, don't override with face
        self._matrix.draw_grid(grid)

        x_count = board.upper().count("X")
        o_count = board.upper().count("O")
        empty = board.count("_") + board.count("-") + board.count(".")

        winner = None
        for a, b, c in _WIN_LINES:
            line = board[a].upper() + board[b].upper() + board[c].upper()
            if line == "XXX":
                winner = "X"
                break
            elif line == "OOO":
                winner = "O"
                break

        status = "in_progress"
        if winner:
            status = f"{winner}_wins"
        elif empty == 0:
            status = "draw"

        return {
            "ok": True,
            "action": "tictactoe",
            "board": board.upper(),
            "x_moves": x_count,
            "o_moves": o_count,
            "empty": empty,
            "status": status,
        }

    async def _run_animation(self, frames: list) -> dict:
        if not isinstance(frames, list) or len(frames) == 0:
            return {"error": "'animation' must be a non-empty list of frames."}
        if len(frames) > 30:
            return {"error": "Animation too long (max 30 frames)."}

        async def _play() -> None:
            try:
                last_grid = None
                for frame in frames:
                    if not isinstance(frame, dict):
                        continue
                    duration_ms = frame.get("duration_ms", 300)

                    face_name = frame.get("face")
                    icon_name = frame.get("icon")
                    if face_name and face_name in FACES:
                        last_grid = FACES[face_name]["closed"]
                        self._matrix.draw_grid(last_grid)
                        self._current_face = face_name
                    elif icon_name and icon_name in BUILTIN_ICONS:
                        last_grid = BUILTIN_ICONS[icon_name]
                        self._matrix.draw_grid(last_grid)
                    elif "pixels" in frame:
                        last_grid = _normalize_grid(frame["pixels"])
                        self._matrix.draw_grid(last_grid)

                    await asyncio.sleep(max(50, min(5000, int(duration_ms))) / 1000.0)

                if last_grid is not None:
                    self._current_custom = last_grid
            except asyncio.CancelledError:
                pass

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
