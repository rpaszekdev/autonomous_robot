"""Configuration loaded from environment + .env file.

Fails fast if required values are missing. Never logs the API key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    google_api_key: str
    gemini_model: str
    simulate_forced: bool
    system_prompt: str
    memory_path: Path
    max_session_seconds: int
    max_sessions_per_hour: int
    session_idle_seconds: int
    input_device: str | None
    output_device: str | None
    gemini_voice: str | None


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required env var {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = _optional(name, "1" if default else "0").lower()
    return raw in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = _optional(name)
    return int(raw) if raw else default


def load() -> Config:
    prompt_path = PROJECT_ROOT / "robot_system_prompt.txt"
    return Config(
        google_api_key=_require("GOOGLE_API_KEY"),
        gemini_model=_optional("GEMINI_MODEL") or "gemini-3.1-flash-live",
        simulate_forced=_bool("SIMULATE", False),
        system_prompt=prompt_path.read_text().strip(),
        memory_path=PROJECT_ROOT / "memory.json",
        max_session_seconds=_int("MAX_SESSION_SECONDS", 120),
        max_sessions_per_hour=_int("MAX_SESSIONS_PER_HOUR", 30),
        session_idle_seconds=_int("SESSION_IDLE_SECONDS", 15),
        input_device=_optional("SD_INPUT_DEVICE") or None,
        output_device=_optional("SD_OUTPUT_DEVICE") or None,
        gemini_voice=_optional("GEMINI_VOICE") or None,
    )
