"""Network mic stream — receives 16kHz mono PCM over TCP from a remote machine.

Drop-in replacement for MicStream when --network-audio is used.
"""

from __future__ import annotations

import array
import asyncio
import logging
import socket
import threading
from typing import Awaitable, Callable

from robot import ui

logger = logging.getLogger(__name__)

MIC_RATE = 16000
MIC_BLOCK = 1600          # 100 ms @ 16 kHz
CHUNK_BYTES = MIC_BLOCK * 2  # 16-bit = 2 bytes per sample
VOICE_RMS_THRESHOLD = 500


def _pcm_rms(pcm: bytes) -> int:
    if len(pcm) < 2:
        return 0
    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    samples = array.array("h")
    samples.frombytes(usable)
    if not samples:
        return 0
    sq = sum(s * s for s in samples)
    return int((sq / len(samples)) ** 0.5)


class NetworkMicStream:
    """Receives 16kHz PCM from a TCP client and feeds it to Gemini."""

    def __init__(
        self,
        on_chunk: Callable[[bytes], Awaitable[None]],
        port: int = 9999,
        on_mute_flush: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._on_chunk = on_chunk
        self._on_mute_flush = on_mute_flush
        self._port = port
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._running = False
        self._muted = False
        self._pending_flush = False
        self._conn: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._dropped = 0
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

    def _tcp_recv_loop(self) -> None:
        """Background thread: accept clients in a loop, auto-reconnect."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self._port))
        srv.listen(1)
        logger.info("[net-mic] Listening on port %d...", self._port)
        ui.info(f"[bold yellow]Waiting for network mic on port {self._port}...[/]")

        while self._running:
            try:
                conn, addr = srv.accept()
            except OSError:
                break
            self._conn = conn
            logger.info("[net-mic] Client connected from %s", addr)
            ui.info(f"[bold green]Network mic connected from {addr}[/]")

            try:
                while self._running:
                    data = b""
                    while len(data) < CHUNK_BYTES:
                        chunk = conn.recv(CHUNK_BYTES - len(data))
                        if not chunk:
                            raise ConnectionError("EOF")
                        data += chunk
                    self._loop.call_soon_threadsafe(self._enqueue, data)
            except (ConnectionError, OSError):
                logger.warning("[net-mic] Client disconnected — waiting for reconnect...")
                ui.info("[bold yellow]Network mic disconnected — waiting for reconnect...[/]")
            finally:
                conn.close()
                self._conn = None

        srv.close()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._tcp_recv_loop, daemon=True)
        self._thread.start()
        logger.info("[net-mic] started — receiving 16kHz PCM over TCP")

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
                    rms = _pcm_rms(chunk)
                    self._real_in_tick += 1
                    self._rms_sum_in_tick += rms
                    if rms > self._rms_peak_in_tick:
                        self._rms_peak_in_tick = rms
                    voice_now = rms > VOICE_RMS_THRESHOLD
                    if voice_now != self._was_voice_active:
                        if voice_now:
                            ui.mic_voice_event("voice_start", rms)
                        else:
                            ui.mic_voice_event("voice_end", rms)
                        self._was_voice_active = voice_now
                    await self._on_chunk(chunk)
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
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
