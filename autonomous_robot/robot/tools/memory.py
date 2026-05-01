"""Persistent memory — global key-value store + per-person profiles.

Storage layout (JSON):
{
  "global": {"house_ssid": "MyWifi", ...},
  "people": {
    "david": {"preferred_language": "English", ...},
    "anna":  {"favorite_music": "jazz", ...}
  }
}

When a person is recognised by face, only global + their own keys are
injected into the system prompt — keeping token usage minimal regardless
of how many people are enrolled.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._active_person: str | None = None

    def set_active_person(self, person_id: str | None) -> None:
        """Called at session start once face recognition completes."""
        self._active_person = person_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text() or "{}")
        except json.JSONDecodeError:
            return {}

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # Tool handler
    # ------------------------------------------------------------------

    async def remember(self, args: dict) -> dict:
        key = args.get("key")
        value = args.get("value")
        if not key or value is None:
            return {"error": "key and value are required"}

        async with self._lock:
            data = self._read()
            if self._active_person:
                data.setdefault("people", {}).setdefault(self._active_person, {})[str(key)] = str(value)
            else:
                data.setdefault("global", {})[str(key)] = str(value)
            self._write(data)

        return {"ok": True, "remembered": {key: value}}

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def snapshot(self, person_id: str | None = None) -> dict[str, str]:
        """Return global memories merged with person-specific memories.

        If person_id is None, only global memories are returned.
        Person keys override global keys on collision.
        """
        data = self._read()
        result: dict[str, str] = dict(data.get("global", {}))
        if person_id:
            result.update(data.get("people", {}).get(person_id, {}))
        return result
