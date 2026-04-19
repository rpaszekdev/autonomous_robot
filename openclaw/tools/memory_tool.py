"""remember tool — Persistent key-value memory store."""

import os
import json
import logging

logger = logging.getLogger(__name__)

MEMORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "memory.json",
)


def _load() -> dict:
    if not os.path.exists(MEMORY_PATH):
        return {}
    try:
        with open(MEMORY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save(data: dict):
    with open(MEMORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def tool_remember(key: str, value: str, **kwargs) -> dict:
    """Store a key-value pair in persistent memory."""
    mem = _load()
    mem[key] = value
    _save(mem)
    logger.info("remember: %s = %s", key, value)
    return {"status": "ok", "key": key, "value": value}
