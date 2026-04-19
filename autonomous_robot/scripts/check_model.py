"""Open a Gemini Live session briefly to validate the model ID."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from robot import config  # noqa: E402


async def main() -> int:
    cfg = config.load()
    print(f"Opening live session with model: {cfg.gemini_model}")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        print(f"[FAIL] SDK import: {exc}")
        return 1

    client = genai.Client(api_key=cfg.google_api_key)
    cfg_obj = types.LiveConnectConfig(response_modalities=["AUDIO"])

    try:
        async with client.aio.live.connect(model=cfg.gemini_model, config=cfg_obj) as session:
            print(f"[ok] session opened: {session}")
    except Exception as exc:
        print(f"[FAIL] could not open live session: {type(exc).__name__}: {exc}")
        print("Common causes:")
        print("  - GEMINI_MODEL in .env is not a valid Live model ID")
        print("  - GOOGLE_API_KEY lacks access to the Live API")
        print("  - Network / firewall")
        return 1
    print("[ok] model accepts Live connections")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
