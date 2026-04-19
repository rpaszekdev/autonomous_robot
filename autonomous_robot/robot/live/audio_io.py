"""Cross-platform audio I/O via sounddevice.

MicStream: 16 kHz int16 mono input → async callback (for Gemini Live send).
SpeakerStream: 24 kHz int16 mono output queue (Gemini Live native rate).
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Awaitable, Callable

import sounddevice as sd

logger = logging.getLogger(__name__)

MIC_RATE = 16000
MIC_BLOCK = 1600   # 100 ms @ 16 kHz
SPK_RATE = 24000
SPK_BLOCK = 2400   # 100 ms @ 24 kHz


class MicStream:
    """Streams microphone PCM16 frames to an async sink."""

    def __init__(
        self,
        on_chunk: Callable[[bytes], Awaitable[None]],
        device: str | int | None = None,
    ) -> None:
        self._on_chunk = on_chunk
        self._device = device
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._stream: sd.RawInputStream | None = None
        self._running = False
        self._dropped = 0

    def _enqueue(self, data: bytes) -> None:
        # Runs on the event loop thread — catch QueueFull here.
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 20 == 1:
                logger.debug("mic backpressure: dropped %d frames", self._dropped)

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("mic status: %s", status)
        data = bytes(indata)
        self._loop.call_soon_threadsafe(self._enqueue, data)

    def start(self) -> None:
        self._stream = sd.RawInputStream(
            samplerate=MIC_RATE,
            channels=1,
            dtype="int16",
            blocksize=MIC_BLOCK,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        self._running = True
        logger.info("[mic] started @ %d Hz mono int16", MIC_RATE)

    async def pump(self) -> None:
        try:
            while self._running:
                chunk = await self._queue.get()
                await self._on_chunk(chunk)
        except asyncio.CancelledError:
            raise

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class SpeakerStream:
    """Async-friendly speaker playback with flushable buffer."""

    def __init__(self, device: str | int | None = None) -> None:
        self._device = device
        self._buffer: deque[bytes] = deque()
        self._lock = asyncio.Lock()
        self._stream: sd.RawOutputStream | None = None

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            logger.debug("speaker status: %s", status)
        needed = frames * 2  # int16 mono
        out = bytearray()
        while len(out) < needed and self._buffer:
            chunk = self._buffer.popleft()
            out.extend(chunk)
        if len(out) < needed:
            out.extend(b"\x00" * (needed - len(out)))
        elif len(out) > needed:
            remainder = bytes(out[needed:])
            out = out[:needed]
            self._buffer.appendleft(remainder)
        outdata[:] = bytes(out)

    def start(self) -> None:
        self._stream = sd.RawOutputStream(
            samplerate=SPK_RATE,
            channels=1,
            dtype="int16",
            blocksize=SPK_BLOCK,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        logger.info("[speaker] started @ %d Hz mono int16", SPK_RATE)

    async def play(self, pcm: bytes) -> None:
        async with self._lock:
            self._buffer.append(pcm)

    async def cancel(self) -> None:
        """Drop any queued audio — used on barge-in / shutdown."""
        async with self._lock:
            self._buffer.clear()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def verify_devices(input_device: str | None, output_device: str | None) -> None:
    """Hard-fail at startup if the audio config is wrong (better than mid-session)."""
    try:
        sd.check_input_settings(
            device=input_device, samplerate=MIC_RATE, channels=1, dtype="int16"
        )
        sd.check_output_settings(
            device=output_device, samplerate=SPK_RATE, channels=1, dtype="int16"
        )
    except sd.PortAudioError as exc:
        raise RuntimeError(
            f"Audio device check failed: {exc}. "
            "On macOS, grant microphone permission in System Settings → "
            "Privacy & Security → Microphone."
        ) from exc
