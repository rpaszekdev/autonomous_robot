"""Tool-call dispatcher: FunctionCall → async handler → result dict."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[dict]]


class ToolDispatcher:
    def __init__(self, handlers: dict[str, Handler]) -> None:
        self._handlers = handlers

    @property
    def names(self) -> list[str]:
        return list(self._handlers.keys())

    async def __call__(self, name: str, args: dict) -> dict:
        handler = self._handlers.get(name)
        if handler is None:
            logger.warning("Unknown tool: %s", name)
            return {"error": f"Unknown tool: {name}"}
        try:
            result = await handler(args)
            logger.info("[tool %s] → %s", name, result)
            return result
        except Exception as exc:  # surface error to the model, don't crash session
            logger.exception("Tool %s failed", name)
            return {"error": str(exc)}
