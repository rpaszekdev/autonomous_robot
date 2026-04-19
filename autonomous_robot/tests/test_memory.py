import asyncio
import json
from pathlib import Path

import pytest

from robot.tools.memory import MemoryStore


@pytest.mark.asyncio
async def test_remember_persists_and_reads_back(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.json")

    r1 = await store.remember({"key": "favorite_color", "value": "blue"})
    r2 = await store.remember({"key": "user_name", "value": "Robert"})

    assert r1["ok"] and r2["ok"]
    snap = store.snapshot()
    assert snap == {"favorite_color": "blue", "user_name": "Robert"}

    reopened = MemoryStore(tmp_path / "memory.json")
    assert reopened.snapshot() == snap


@pytest.mark.asyncio
async def test_remember_requires_key_and_value(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.json")
    assert "error" in await store.remember({"key": "", "value": "x"})
    assert "error" in await store.remember({"key": "k"})
