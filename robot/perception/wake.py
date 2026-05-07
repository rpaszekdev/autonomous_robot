"""Wake-word triggers: keyboard Enter (dev) or openWakeWord (Pi)."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Protocol

logger = logging.getLogger(__name__)


class Wake(Protocol):
    async def wait(self) -> None: ...
    def stop(self) -> None: ...


def _make_event_setter(loop: asyncio.AbstractEventLoop, event: asyncio.Event):
    def set_event() -> None:
        loop.call_soon_threadsafe(event.set)
    return set_event


class KeyboardWake:
    """Press Enter to wake. Used on Mac and in --simulate."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._event = asyncio.Event()
        self._running = True
        self._thread = threading.Thread(target=self._loop_stdin, daemon=True)
        self._thread.start()
        logger.info("[wake] keyboard trigger active — press ENTER to talk")

    def _loop_stdin(self) -> None:
        set_event = _make_event_setter(self._loop, self._event)
        while self._running:
            try:
                input()  # wake prompt is rendered by runtime via ui module
            except (EOFError, KeyboardInterrupt):
                return
            set_event()

    async def wait(self) -> None:
        await self._event.wait()
        self._event.clear()

    def stop(self) -> None:
        self._running = False


class OpenWakeWordWake:
    """Real wake-word detection using openWakeWord (Pi)."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        model_path: str,
        threshold: float = 0.7,
    ) -> None:
        import pyaudio
        from openwakeword.model import Model

        self._loop = loop
        self._event = asyncio.Event()
        self._threshold = threshold
        self._model = Model(wakeword_model_paths=[model_path])
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1280,
        )
        self._running = True
        self._thread = threading.Thread(target=self._loop_audio, daemon=True)
        self._thread.start()
        logger.info("[wake] openWakeWord active (threshold=%.2f)", threshold)

    def _loop_audio(self) -> None:
        import numpy as np

        set_event = _make_event_setter(self._loop, self._event)
        while self._running:
            try:
                frame = self._stream.read(1280, exception_on_overflow=False)
            except OSError:
                continue
            samples = np.frombuffer(frame, dtype=np.int16)
            scores = self._model.predict(samples)
            if max(scores.values(), default=0.0) >= self._threshold:
                logger.info("[wake] wake word detected")
                set_event()

    async def wait(self) -> None:
        await self._event.wait()
        self._event.clear()

    def stop(self) -> None:
        self._running = False
        try:
            self._stream.stop_stream()
            self._stream.close()
            self._pa.terminate()
        except Exception:
            pass
