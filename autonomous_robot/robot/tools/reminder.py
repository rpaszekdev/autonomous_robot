"""set_reminder() handler — schedules a spoken message via asyncio."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Speaker = Callable[[str], Awaitable[None]]


class ReminderService:
    def __init__(self, speak: Speaker) -> None:
        self._speak = speak
        self._tasks: set[asyncio.Task] = set()

    async def schedule(self, args: dict) -> dict:
        message = args.get("message")
        delay = args.get("delay_seconds")
        if not message or delay is None:
            return {"error": "message and delay_seconds are required"}
        try:
            delay_s = max(0, int(delay))
        except (TypeError, ValueError):
            return {"error": "delay_seconds must be an integer"}

        async def fire() -> None:
            await asyncio.sleep(delay_s)
            logger.info("[reminder] firing: %s", message)
            await self._speak(str(message))

        task = asyncio.create_task(fire())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"ok": True, "scheduled_in_seconds": delay_s}

    def cancel_all(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
