"""Server-side tic-tac-toe engine.

All game logic runs here — Gemini only interprets the human's move
as a position (1-9) and calls ttt_move(position=N). Board state
survives session reconnects because the engine lives outside the
reconnect loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from robot.tools.display import DisplayToolService

logger = logging.getLogger(__name__)

_WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


class TicTacToeEngine:
    def __init__(self, display: DisplayToolService) -> None:
        self._display = display
        self._board: list[str] = ["_"] * 9
        self._active = False

    def _board_str(self) -> str:
        return "".join(self._board)

    def _check_winner(self) -> str | None:
        for a, b, c in _WIN_LINES:
            if self._board[a] == self._board[b] == self._board[c] != "_":
                return self._board[a]
        return None

    def _is_draw(self) -> bool:
        return "_" not in self._board

    def _best_o_move(self) -> int:
        best_score = -2
        best_pos = -1
        for i in range(9):
            if self._board[i] != "_":
                continue
            self._board[i] = "O"
            score = self._minimax(False, -2, 2)
            self._board[i] = "_"
            if score > best_score:
                best_score = score
                best_pos = i
        return best_pos

    def _minimax(self, is_maximizing: bool, alpha: int, beta: int) -> int:
        winner = self._check_winner()
        if winner == "O":
            return 1
        if winner == "X":
            return -1
        if self._is_draw():
            return 0

        if is_maximizing:
            best = -2
            for i in range(9):
                if self._board[i] != "_":
                    continue
                self._board[i] = "O"
                val = self._minimax(False, alpha, beta)
                self._board[i] = "_"
                best = max(best, val)
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
            return best
        else:
            best = 2
            for i in range(9):
                if self._board[i] != "_":
                    continue
                self._board[i] = "X"
                val = self._minimax(True, alpha, beta)
                self._board[i] = "_"
                best = min(best, val)
                beta = min(beta, val)
                if beta <= alpha:
                    break
            return best

    def _render(self) -> None:
        self._display.show_tictactoe(self._board_str())

    def _unpin_later(self) -> None:
        async def _unpin() -> None:
            await asyncio.sleep(2)
            self._display._pinned = False
            self._display._current_face = "happy"
            from robot.tools.display import FACES
            self._display._matrix.draw_grid(FACES["happy"]["closed"])

        asyncio.get_event_loop().create_task(_unpin(), name="ttt_unpin")

    async def start(self, args: dict) -> dict:
        self._board = ["_"] * 9
        self._active = True
        self._render()
        return {
            "ok": True,
            "board": self._board_str(),
            "status": "in_progress",
            "message": "New game started. Board is empty. Human is X, robot is O. Ask the human to make their move (positions 1-9).",
        }

    async def move(self, args: dict) -> dict:
        if not self._active:
            return {"error": "No game in progress. Call ttt_start first."}

        pos = args.get("position")
        if pos is None:
            return {"error": "Missing 'position' parameter (1-9)."}
        try:
            pos = int(pos)
        except (TypeError, ValueError):
            return {"error": f"Invalid position '{pos}'. Must be 1-9."}
        if pos < 1 or pos > 9:
            return {"error": f"Position {pos} out of range. Must be 1-9."}

        idx = pos - 1
        if self._board[idx] != "_":
            return {
                "error": f"Position {pos} is already occupied by {self._board[idx]}.",
                "board": self._board_str(),
            }

        # Place X (human)
        self._board[idx] = "X"
        x_move = pos

        # Check if human won or draw
        winner = self._check_winner()
        if winner:
            self._active = False
            self._render()
            self._unpin_later()
            return {
                "ok": True,
                "board": self._board_str(),
                "x_move": x_move,
                "o_move": None,
                "status": "X_wins",
            }
        if self._is_draw():
            self._active = False
            self._render()
            self._unpin_later()
            return {
                "ok": True,
                "board": self._board_str(),
                "x_move": x_move,
                "o_move": None,
                "status": "draw",
            }

        # Compute and place O (robot)
        o_idx = self._best_o_move()
        self._board[o_idx] = "O"
        o_move = o_idx + 1

        # Check if robot won or draw
        winner = self._check_winner()
        status = "in_progress"
        if winner:
            status = "O_wins"
            self._active = False
        elif self._is_draw():
            status = "draw"
            self._active = False

        self._render()

        if not self._active:
            self._unpin_later()

        return {
            "ok": True,
            "board": self._board_str(),
            "x_move": x_move,
            "o_move": o_move,
            "status": status,
        }
