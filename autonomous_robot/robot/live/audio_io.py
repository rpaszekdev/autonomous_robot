"""Cross-platform audio I/O via sounddevice.

MicStream: 16 kHz int16 mono input → async callback (for Gemini Live send).
SpeakerStream: 24 kHz int16 mono output queue (Gemini Live native rate).
"""

from __future__ import annotations

import array
import asyncio
import logging
import os
from collections import deque
from typing import Awaitable, Callable

import sounddevice as sd

from robot import ui

logger = logging.getLogger(__name__)

MIC_RATE = 16000
MIC_BLOCK = 1600   # 100 ms @ 16 kHz
SPK_RATE = 24000
SPK_BLOCK = 2400   # 100 ms @ 24 kHz

# Client-side voice-onset threshold for diagnostic log line only.
# Does not affect what is sent to Gemini — server runs its own VAD.
VOICE_RMS_THRESHOLD = 500

DEBUG_LIVE = os.environ.get("DEBUG_LIVE", "1") == "1"


def _pcm_rms(pcm: bytes) -> int:
    """Root-mean-square of int16 mono PCM — cheap energy proxy."""
    if len(pcm) < 2:
        return 0
    # Trim any odd trailing byte (int16 = 2 bytes per sample).
    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    samples = array.array("h")
    samples.frombytes(usable)
    if not samples:
        return 0
    sq = 0
    for s in samples:
        sq += s * s
    return int((sq / len(samples)) ** 0.5)


class MicStream:
    """Streams microphone PCM16 frames to an async sink."""

    def __init__(
        self,
        on_chunk: Callable[[bytes], Awaitable[None]],
        device: str | int | None = None,
        on_mute_flush: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._on_chunk = on_chunk
        self._on_mute_flush = on_mute_flush
        self._device = device
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._stream: sd.RawInputStream | None = None
        self._running = False
        self._dropped = 0
        self._muted = False
        self._pending_flush = False
        # Debug rollup state
        self._real_in_tick = 0
        self._silent_in_tick = 0
        self._rms_sum_in_tick = 0
        self._rms_peak_in_tick = 0
        self._tick_start: float = 0.0
        self._was_voice_active = False

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
        import time

        self._tick_start = time.monotonic()
        try:
            while self._running:
                chunk = await self._queue.get()
                # On transition INTO mute we fire audio_stream_end exactly
                # once so the server flushes its VAD buffer cleanly. Per
                # Gemini Live docs: pauses >1s require audio_stream_end,
                # otherwise the VAD stays wedged and the next turn never
                # triggers a response.
                if self._pending_flush and self._on_mute_flush is not None:
                    self._pending_flush = False
                    await self._on_mute_flush()
                if self._muted:
                    # Drop frames entirely — real pause, not silence.
                    # audio_stream_end already told the server "user is
                    # done," so the server cleanly closes the turn and
                    # waits for the next voice onset.
                    self._silent_in_tick += 1
                else:
                    rms = _pcm_rms(chunk) if DEBUG_LIVE else 0
                    self._real_in_tick += 1
                    self._rms_sum_in_tick += rms
                    if rms > self._rms_peak_in_tick:
                        self._rms_peak_in_tick = rms

                    # Detect client-side voice onset/offset transitions
                    voice_now = rms > VOICE_RMS_THRESHOLD
                    if DEBUG_LIVE and voice_now != self._was_voice_active:
                        if voice_now:
                            ui.mic_voice_event("voice_start", rms)
                        else:
                            ui.mic_voice_event("voice_end", rms)
                        self._was_voice_active = voice_now

                    await self._on_chunk(chunk)

                # One-second rollup log
                if DEBUG_LIVE:
                    now = time.monotonic()
                    if now - self._tick_start >= 1.0:
                        total = self._real_in_tick + self._silent_in_tick
                        avg = (
                            self._rms_sum_in_tick // max(self._real_in_tick, 1)
                        )
                        ui.mic_tick(
                            self._real_in_tick,
                            self._silent_in_tick,
                            avg,
                            self._rms_peak_in_tick,
                        )
                        self._real_in_tick = 0
                        self._silent_in_tick = 0
                        self._rms_sum_in_tick = 0
                        self._rms_peak_in_tick = 0
                        self._tick_start = now
        except asyncio.CancelledError:
            raise

    def set_muted(self, muted: bool) -> None:
        """Drop incoming audio while muted. On the mute transition we drain
        any stale PCM already queued so it can't leak out later, and we
        queue an audio_stream_end flush so the server's VAD closes turn 1
        cleanly. On unmute we do NOT drain — chunks arriving right at the
        transition are the start of the user's reply and must reach the
        server."""
        was_muted = self._muted
        self._muted = muted
        if muted and not was_muted:
            self._drain_queue()
            self._pending_flush = True

    def _drain_queue(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

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
