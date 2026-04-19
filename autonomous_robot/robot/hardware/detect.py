"""Runtime detection: Raspberry Pi vs other (Mac/dev)."""

from __future__ import annotations

from pathlib import Path


def is_raspberry_pi() -> bool:
    model = Path("/proc/device-tree/model")
    try:
        return "Raspberry Pi" in model.read_text(errors="ignore")
    except OSError:
        return False


def should_simulate(force: bool) -> bool:
    return force or not is_raspberry_pi()
