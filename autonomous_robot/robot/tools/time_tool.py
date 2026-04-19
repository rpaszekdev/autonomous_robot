"""get_time() handler."""

from __future__ import annotations

from datetime import datetime


async def handle(args: dict) -> dict:
    now = datetime.now()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "human": now.strftime("%A %B %d %Y, %H:%M"),
    }
