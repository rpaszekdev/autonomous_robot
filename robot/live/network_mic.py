"""Network mic stream — receives 16kHz mono PCM over TCP from a remote machine.

Drop-in replacement for MicStream when --network-audio is used.
The TCP connection persists across Gemini session reconnects — only the
chunk callback is swapped via prepare_session().
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
    """Receives 16kHz PCM from a TCP client and feeds it to Gemini.

    Lifecycle:
        net_mic = NetworkMicStream(port=9999)
        net_mic.start()                          # starts TCP thread once

        # For each Gemini session:
        net_mic.prepare_session(on_chunk, on_mute_flush)
        await net_mic.pump()                     # cancelled when session ends

        net_mic.stop()                           # final cleanup
    """

    def __init__(self, port: int = 9999) -> None:
        self._port = port
        self._on_chunk: Callable[[bytes], Awaitable[None]] | None = None
        self._on_mute_flush: Callable[[], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[bytes] | None = None
        self._running = False
        self._muted = False
        self._pending_flush = False
        self._conn: socket.socket | None = None
        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._dropped = 0
        self._real_in_tick = 0
        self._silent_in_tick = 0
        self._rms_sum_in_tick = 0
        self._rms_peak_in_tick = 0
        self._tick_start: float = 0.0
        self._was_voice_active = False

    def prepare_session(
        self,
        on_chunk: Callable[[bytes], Awaitable[None]],
        on_mute_flush: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Swap callbacks for a new Gemini session. Drains stale audio."""
        self._on_chunk = on_chunk
        self._on_mute_flush = on_mute_flush
        self._muted = False
        self._pending_flush = False
        self._drain_queue()

    def _enqueue(self, data: bytes) -> None:
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            self._dropped += 1

    def _tcp_recv_loop(self) -> None:
        """Background thread: accept clients in a loop, auto-reconnect."""
        import time
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self._port))
        srv.listen(1)
        self._srv = srv
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

            recv_count = 0
            recv_bytes = 0
            partial_reads = 0
            t0 = time.monotonic()
            try:
                while self._running:
                    data = b""
                    reads_for_chunk = 0
                    while len(data) < CHUNK_BYTES:
                        chunk = conn.recv(CHUNK_BYTES - len(data))
                        if not chunk:
                            raise ConnectionError("EOF")
                        reads_for_chunk += 1
                        data += chunk
                    if reads_for_chunk > 1:
                        partial_reads += 1
                    recv_count += 1
                    recv_bytes += len(data)
                    if self._loop and self._queue:
                        self._loop.call_soon_threadsafe(self._enqueue, data)
                    # Log stats every 5 seconds
                    now = time.monotonic()
                    if now - t0 >= 5.0:
                        elapsed = now - t0
                        qsize = self._queue.qsize() if self._queue else -1
                        logger.info(
                            "[net-mic] TCP recv: %d chunks (%.1f/s), %d bytes, "
                            "%d partial reads, queue=%d, dropped=%d",
                            recv_count, recv_count / elapsed,
                            recv_bytes, partial_reads, qsize, self._dropped,
                        )
                        recv_count = 0
                        recv_bytes = 0
                        partial_reads = 0
                        t0 = now
            except (ConnectionError, OSError) as e:
                logger.warning("[net-mic] Client disconnected (%s) — waiting for reconnect...", e)
                ui.info("[bold yellow]Network mic disconnected — waiting for reconnect...[/]")
            finally:
                conn.close()
                self._conn = None

        srv.close()

    def start(self) -> None:
        """Start the TCP receiver thread. Call once at startup."""
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=128)
        self._running = True
        self._thread = threading.Thread(target=self._tcp_recv_loop, daemon=True)
        self._thread.start()
        logger.info("[net-mic] started — receiving 16kHz PCM over TCP")

    async def pump(self) -> None:
        """Forward queued audio to the current session callback.

        Safe to call repeatedly — each Gemini session starts a new pump().
        Cancelled when the TaskGroup tears down.
        """
        import time
        self._tick_start = time.monotonic()
        pump_chunks = 0
        pump_bytes = 0
        pump_t0 = time.monotonic()
        try:
            while self._running:
                chunk = await self._queue.get()
                pump_chunks += 1
                pump_bytes += len(chunk)
                if self._on_chunk is None:
                    continue
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
                now = time.monotonic()
                if now - self._tick_start >= 1.0:
                    avg = self._rms_sum_in_tick // max(self._real_in_tick, 1)
                    ui.mic_tick(self._real_in_tick, self._silent_in_tick, avg, self._rms_peak_in_tick)
                    self._real_in_tick = 0
                    self._silent_in_tick = 0
                    self._rms_sum_in_tick = 0
                    self._rms_peak_in_tick = 0
                    self._tick_start = now
                # Log pump throughput every 5s
                if now - pump_t0 >= 5.0:
                    elapsed = now - pump_t0
                    qsize = self._queue.qsize() if self._queue else -1
                    logger.info(
                        "[net-mic] pump: %d chunks forwarded (%.1f/s), %d bytes, "
                        "queue=%d, muted=%s",
                        pump_chunks, pump_chunks / elapsed,
                        pump_bytes, qsize, self._muted,
                    )
                    pump_chunks = 0
                    pump_bytes = 0
                    pump_t0 = now
        except asyncio.CancelledError:
            raise

    def set_muted(self, muted: bool) -> None:
        was_muted = self._muted
        self._muted = muted
        if muted and not was_muted:
            self._drain_queue()
            self._pending_flush = True

    def _drain_queue(self) -> None:
        if self._queue is None:
            return
        try:
            while True:
                self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    def stop(self) -> None:
        """Full shutdown — close TCP server. Call once at final cleanup."""
        self._running = False
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        if self._srv:
            try:
                self._srv.close()
            except Exception:
                pass
