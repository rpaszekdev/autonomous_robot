"""Persistent memory: flat JSON key-value store."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text() or "{}")
        except json.JSONDecodeError:
            return {}

    def _write(self, data: dict[str, str]) -> None:
        self._path.write_text(json.dumps(data, indent=2))

    async def remember(self, args: dict) -> dict:
        key = args.get("key")
        value = args.get("value")
        if not key or value is None:
            return {"error": "key and value are required"}
        async with self._lock:
            data = self._read()
            data[str(key)] = str(value)
            self._write(data)
        return {"ok": True, "remembered": {key: value}}

    def set_active_person(self, person_id: str | None) -> None:
        """Set the active person for per-person memory scoping."""
        self._active_person = person_id

    def snapshot(self, **kwargs) -> dict[str, str]:
        return self._read()
