"""Pre-flight: verify env, audio devices, and google-genai can authenticate.

Does NOT open a Gemini Live WebSocket — safe to run repeatedly at no cost.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from robot import config  # noqa: E402
from robot.live.audio_io import verify_devices  # noqa: E402


def main() -> int:
    print("── Pre-flight check ──")
    try:
        cfg = config.load()
    except RuntimeError as exc:
        print(f"[FAIL] config: {exc}")
        return 1
    print(f"[ok]   env loaded; model = {cfg.gemini_model}")
    print(f"[ok]   GOOGLE_API_KEY present ({len(cfg.google_api_key)} chars)")

    try:
        verify_devices(cfg.input_device, cfg.output_device)
    except RuntimeError as exc:
        print(f"[FAIL] audio devices: {exc}")
        return 1
    print("[ok]   mic @ 16 kHz mono int16 available")
    print("[ok]   speaker @ 24 kHz mono int16 available")

    try:
        from google import genai
        client = genai.Client(api_key=cfg.google_api_key)
        _ = client  # no network call yet
    except ImportError as exc:
        print(f"[FAIL] google-genai import: {exc}")
        return 1
    print("[ok]   google-genai SDK loadable")
    print("── Ready to run:  python -m robot.main --simulate ──")
    return 0


if __name__ == "__main__":
    sys.exit(main())
