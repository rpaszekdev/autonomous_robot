"""speak() handler — acknowledges the call.

Gemini Live's native audio response is the actual speech channel. The
model may still emit this tool if the system prompt suggests it, so we
accept gracefully rather than erroring.
"""

from __future__ import annotations


async def handle(args: dict) -> dict:
    text = args.get("text", "")
    return {"ok": True, "note": "Native audio output was used; text noted.", "echoed": text[:200]}
