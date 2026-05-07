"""Cross-platform audio I/O via sounddevice.

MicStream: records at hardware rate, resamples to 16 kHz for Gemini Live.
SpeakerStream: receives 24 kHz from Gemini, resamples to hardware rate for HDMI.
"""

from __future__ import annotations

import array
import asyncio
import logging
import os
import struct
from collections import deque
from typing import Awaitable, Callable

import socket
import threading
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

from robot import ui

logger = logging.getLogger(__name__)

MIC_RATE = 16000          # Rate Gemini expects
MIC_HW_RATE = 48000       # BOYA mini native rate
MIC_BLOCK = 1600          # 100 ms @ 16 kHz (sent to Gemini)
MIC_HW_BLOCK = 4800       # 100 ms @ 48 kHz (captured from mic)

SPK_RATE = 24000          # Rate Gemini sends
SPK_HW_RATE = 48000       # HDMI native rate
SPK_BLOCK = 2400          # 100 ms @ 24 kHz
SPK_HW_BLOCK = 4800       # 100 ms @ 48 kHz

VOICE_RMS_THRESHOLD = 500
DEBUG_LIVE = os.environ.get("DEBUG_LIVE", "0") == "1"

# Device indices
MIC_DEVICE = "BOYA mini: USB Audio"   # ALSA device name
SPK_DEVICE = None                      # default ALSA output (HDMI)


def _pcm_rms(pcm: bytes) -> int:
    if len(pcm) < 2:
        return 0
    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    samples = array.array("h")
    samples.frombytes(usable)
    if not samples:
        return 0
    sq = 0
    for s in samples:
        sq += s * s
    return int((sq / len(samples)) ** 0.5)


def _resample(data: bytes, in_rate: int, out_rate: int) -> bytes:
    """Resample int16 mono PCM."""
    from math import gcd
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    g = gcd(out_rate, in_rate)
    up, down = out_rate // g, in_rate // g
    resampled = resample_poly(samples, up, down)
    return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()


class MicStream:
    def __init__(
        self,
        on_chunk: Callable[[bytes], Awaitable[None]],
        device: str | int | None = None,
        on_mute_flush: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._on_chunk = on_chunk
        self._on_mute_flush = on_mute_flush
        self._device = MIC_DEVICE  # always use BOYA mini
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._stream: sd.RawInputStream | None = None
        self._running = False
        self._dropped = 0
        self._muted = False
        self._pending_flush = False
        self._real_in_tick = 0
        self._silent_in_tick = 0
        self._rms_sum_in_tick = 0
        self._rms_peak_in_tick = 0
        self._tick_start: float = 0.0
        self._was_voice_active = False

    def _enqueue(self, data: bytes) -> None:
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            self._dropped += 1

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("mic status: %s", status)
        raw = bytes(indata)
        # Resample 48000 Hz → 16000 Hz for Gemini
        resampled = _resample(raw, MIC_HW_RATE, MIC_RATE)
        self._loop.call_soon_threadsafe(self._enqueue, resampled)

    def start(self) -> None:
        self._stream = sd.RawInputStream(
            samplerate=MIC_HW_RATE,
            channels=1,
            dtype="int16",
            blocksize=MIC_HW_BLOCK,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        self._running = True
        logger.info("[mic] started @ %d Hz (resampling to %d Hz for Gemini)", MIC_HW_RATE, MIC_RATE)

    async def pump(self) -> None:
        import time
        self._tick_start = time.monotonic()
        try:
            while self._running:
                chunk = await self._queue.get()
                if self._pending_flush and self._on_mute_flush is not None:
                    self._pending_flush = False
                    await self._on_mute_flush()
                if self._muted:
                    self._silent_in_tick += 1
                else:
                    rms = _pcm_rms(chunk) if DEBUG_LIVE else 0
                    self._real_in_tick += 1
                    self._rms_sum_in_tick += rms
                    if rms > self._rms_peak_in_tick:
                        self._rms_peak_in_tick = rms
                    voice_now = rms > VOICE_RMS_THRESHOLD
                    if DEBUG_LIVE and voice_now != self._was_voice_active:
                        if voice_now:
                            ui.mic_voice_event("voice_start", rms)
                        else:
                            ui.mic_voice_event("voice_end", rms)
                        self._was_voice_active = voice_now
                    await self._on_chunk(chunk)
                if DEBUG_LIVE:
                    import time as _time
                    now = _time.monotonic()
                    if now - self._tick_start >= 1.0:
                        avg = self._rms_sum_in_tick // max(self._real_in_tick, 1)
                        ui.mic_tick(self._real_in_tick, self._silent_in_tick, avg, self._rms_peak_in_tick)
                        self._real_in_tick = 0
                        self._silent_in_tick = 0
                        self._rms_sum_in_tick = 0
                        self._rms_peak_in_tick = 0
                        self._tick_start = now
        except asyncio.CancelledError:
            raise

    def set_muted(self, muted: bool) -> None:
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
    def __init__(self, device: str | int | None = None) -> None:
        self._device = device
        self._buffer: deque[bytes] = deque()
        self._lock = threading.Lock()
        self._stream: sd.RawOutputStream | None = None
        self._available = False
        self._clients: list[socket.socket] = []
        self._server_thread = threading.Thread(target=self._tcp_server, daemon=True)
        self._server_thread.start()

    def _tcp_server(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", 9001))
        srv.listen(5)
        logger.info("[speaker] TCP audio stream on port 9001")
        while True:
            try:
                conn, addr = srv.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                logger.info("[speaker] client connected from %s", addr)
                self._clients.append(conn)
            except Exception:
                break

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            logger.debug("speaker status: %s", status)
        needed = frames * 2
        out = bytearray()
        with self._lock:
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
        try:
            self._stream = sd.RawOutputStream(
                samplerate=SPK_HW_RATE,
                channels=1,
                dtype="int16",
                blocksize=SPK_HW_BLOCK,
                device=self._device,
                callback=self._callback,
            )
            self._stream.start()
            self._available = True
            logger.info("[speaker] started @ %d Hz (Gemini @ %d Hz, resampling)", SPK_HW_RATE, SPK_RATE)
        except Exception as e:
            logger.warning("[speaker] no output device available: %s", e)
            self._available = False

    def _open_fifo(self):
        try:
            if not hasattr(self, "_fifo") or self._fifo is None:
                self._fifo = open("/tmp/robot_audio.fifo", "wb", buffering=0)
        except Exception:
            self._fifo = None

    async def play(self, pcm: bytes) -> None:
        self._open_fifo()
        if hasattr(self, "_fifo") and self._fifo:
            try:
                self._fifo.write(pcm)
            except Exception:
                self._fifo = None
        # Always stream length-prefixed 24kHz PCM to TCP clients (Mac speaker)
        dead = []
        framed = struct.pack(">I", len(pcm)) + pcm
        for c in self._clients:
            try:
                c.sendall(framed)
            except Exception:
                dead.append(c)
        for c in dead:
            self._clients.remove(c)
        if not self._available:
            return
        resampled = _resample(pcm, SPK_RATE, SPK_HW_RATE)
        with self._lock:
            self._buffer.append(resampled)

    async def cancel(self) -> None:
        with self._lock:
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
    """Verify audio devices — log warnings instead of hard-failing on rate mismatch."""
    try:
        sd.check_input_settings(
            device=MIC_DEVICE, samplerate=MIC_HW_RATE, channels=1, dtype="int16"
        )
        logger.info("[audio] mic OK: %s @ %d Hz", MIC_DEVICE, MIC_HW_RATE)
    except sd.PortAudioError as exc:
        logger.warning("[audio] mic check failed: %s", exc)

    try:
        sd.check_output_settings(
            device=output_device, samplerate=SPK_HW_RATE, channels=1, dtype="int16"
        )
        logger.info("[audio] speaker OK @ %d Hz", SPK_HW_RATE)
    except sd.PortAudioError as exc:
        logger.warning("[audio] speaker check failed: %s — audio output may not work", exc)
