"""Simulate the Pi↔Mac network audio pipeline locally.

Reproduces the audio cutoff/crash by running:
  - A fake "Pi mic server" (TCP:9999) that accepts mic audio from mac_mic_sender
  - A fake "Pi speaker server" (TCP:9001) that streams audio to play_robot_audio
  - Configurable network jitter (artificial delays) to simulate WiFi

Run:
    python tests/test_network_audio.py                  # clean network
    python tests/test_network_audio.py --jitter 50      # 50ms jitter spikes
    python tests/test_network_audio.py --jitter 200     # 200ms (will crash sender)
    python tests/test_network_audio.py --duration 30    # run for 30 seconds
"""

from __future__ import annotations

import argparse
import collections
import os
import queue
import random
import socket
import struct
import sys
import threading
import time

MIC_RATE = 16000
MIC_CHUNK_BYTES = 1600 * 2  # 100ms @ 16kHz int16
SPK_RATE = 24000
SPK_CHUNK_BYTES = 2400 * 2  # 100ms @ 24kHz int16

MIC_PORT = 19999   # use high ports to avoid conflict with real services
SPK_PORT = 19001


class Stats:
    def __init__(self, name: str):
        self.name = name
        self.lock = threading.Lock()
        self.chunks = 0
        self.bytes = 0
        self.drops = 0
        self.errors = 0
        self.max_latency_ms = 0.0
        self.jitter_events = 0
        self.t0 = time.monotonic()

    def record(self, nbytes: int, latency_ms: float = 0.0):
        with self.lock:
            self.chunks += 1
            self.bytes += nbytes
            if latency_ms > self.max_latency_ms:
                self.max_latency_ms = latency_ms

    def record_drop(self):
        with self.lock:
            self.drops += 1

    def record_error(self):
        with self.lock:
            self.errors += 1

    def record_jitter(self):
        with self.lock:
            self.jitter_events += 1

    def report(self) -> str:
        with self.lock:
            elapsed = time.monotonic() - self.t0
            rate = self.chunks / max(elapsed, 0.001)
            msg = (
                f"[{self.name}] {self.chunks} chunks ({rate:.1f}/s) "
                f"{self.bytes} bytes | drops={self.drops} errors={self.errors} "
                f"max_lat={self.max_latency_ms:.1f}ms jitter_hits={self.jitter_events}"
            )
            self.chunks = 0
            self.bytes = 0
            self.drops = 0
            self.errors = 0
            self.max_latency_ms = 0.0
            self.jitter_events = 0
            self.t0 = time.monotonic()
            return msg


def generate_tone_pcm(sample_rate: int, chunk_samples: int, freq: float = 440.0) -> bytes:
    import math
    buf = bytearray(chunk_samples * 2)
    for i in range(chunk_samples):
        val = int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
        struct.pack_into("<h", buf, i * 2, val)
    return bytes(buf)


def fake_pi_mic_server(
    port: int,
    jitter_ms: int,
    stop: threading.Event,
    stats: Stats,
):
    """Simulates the Pi's network_mic TCP server on port 9999.
    Accepts connections and reads mic audio, applying jitter to simulate slow reads.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.settimeout(1.0)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    print(f"[fake-pi-mic] listening on :{port}")

    while not stop.is_set():
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        print(f"[fake-pi-mic] client connected: {addr}")
        conn.settimeout(2.0)
        try:
            while not stop.is_set():
                data = b""
                t0 = time.monotonic()
                while len(data) < MIC_CHUNK_BYTES:
                    try:
                        chunk = conn.recv(MIC_CHUNK_BYTES - len(data))
                    except socket.timeout:
                        stats.record_error()
                        continue
                    if not chunk:
                        raise ConnectionError("EOF")
                    data += chunk
                latency = (time.monotonic() - t0) * 1000
                stats.record(len(data), latency)

                # simulate jitter: randomly delay reading next chunk
                if jitter_ms > 0 and random.random() < 0.15:
                    delay = random.uniform(0, jitter_ms / 1000)
                    stats.record_jitter()
                    time.sleep(delay)
        except (ConnectionError, OSError) as e:
            print(f"[fake-pi-mic] client disconnected: {e}")
            stats.record_error()
        finally:
            conn.close()
    srv.close()


def fake_pi_speaker_server(
    port: int,
    jitter_ms: int,
    stop: threading.Event,
    stats: Stats,
):
    """Simulates the Pi sending Gemini's speech audio on TCP:9001.
    Generates a 440Hz tone and streams it at real-time rate.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.settimeout(1.0)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    print(f"[fake-pi-spk] listening on :{port}")

    tone = generate_tone_pcm(SPK_RATE, 2400, freq=440.0)

    while not stop.is_set():
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        print(f"[fake-pi-spk] client connected: {addr}")
        try:
            chunk_duration = 2400 / SPK_RATE  # 0.1s per chunk
            next_send = time.monotonic()
            while not stop.is_set():
                now = time.monotonic()
                if now < next_send:
                    time.sleep(next_send - now)

                # simulate jitter: randomly stall the send
                if jitter_ms > 0 and random.random() < 0.15:
                    delay = random.uniform(0, jitter_ms / 1000)
                    stats.record_jitter()
                    time.sleep(delay)

                t0 = time.monotonic()
                conn.sendall(tone)
                latency = (time.monotonic() - t0) * 1000
                stats.record(len(tone), latency)
                next_send += chunk_duration
        except (ConnectionError, OSError, BrokenPipeError) as e:
            print(f"[fake-pi-spk] client disconnected: {e}")
            stats.record_error()
        finally:
            conn.close()
    srv.close()


def mic_sender_under_test(
    host: str,
    port: int,
    stop: threading.Event,
    stats: Stats,
):
    """Replays the same logic as mac_mic_sender.py but with synthetic audio.
    Tests whether sendall() inside the callback causes crashes.
    """
    tone = generate_tone_pcm(MIC_RATE, 1600, freq=300.0)
    chunk_duration = 1600 / MIC_RATE  # 0.1s

    while not stop.is_set():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            print(f"[mic-sender] connected to {host}:{port}")
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
            sock.close()
            continue

        try:
            next_send = time.monotonic()
            while not stop.is_set():
                now = time.monotonic()
                if now < next_send:
                    time.sleep(next_send - now)
                t0 = time.monotonic()
                sock.sendall(tone)
                latency = (time.monotonic() - t0) * 1000
                stats.record(len(tone), latency)

                if latency > 10:
                    print(f"  [mic-sender] SLOW sendall: {latency:.1f}ms (>10ms = would crash real callback)")

                next_send += chunk_duration
        except (BrokenPipeError, OSError) as e:
            print(f"[mic-sender] connection lost: {e}")
            stats.record_error()
        finally:
            sock.close()


def speaker_receiver_under_test(
    host: str,
    port: int,
    stop: threading.Event,
    stats: Stats,
):
    """Replays play_robot_audio.py logic: connect, pre-buffer, track underruns."""
    PRE_BUFFER = 3
    buf = collections.deque()
    underruns = 0
    playback_started = False

    while not stop.is_set():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((host, port))
            print(f"[spk-recv] connected to {host}:{port}")
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
            sock.close()
            continue

        leftover = b""
        pre_buffered = 0
        playback_started = False
        buf.clear()

        # Simulate the playback callback consuming at real-time rate
        consume_interval = 2400 / SPK_RATE
        last_consume = time.monotonic()

        try:
            while not stop.is_set():
                try:
                    chunk = sock.recv(8192)
                except socket.timeout:
                    continue
                if not chunk:
                    break

                leftover += chunk
                while len(leftover) >= SPK_CHUNK_BYTES:
                    frame = leftover[:SPK_CHUNK_BYTES]
                    leftover = leftover[SPK_CHUNK_BYTES:]
                    buf.append(frame)
                    stats.record(len(frame))

                    if not playback_started:
                        pre_buffered += 1
                        if pre_buffered >= PRE_BUFFER:
                            playback_started = True
                            print(f"[spk-recv] pre-buffer filled ({PRE_BUFFER} frames), playback started")

                # Simulate playback consumption
                now = time.monotonic()
                while now - last_consume >= consume_interval:
                    last_consume += consume_interval
                    if buf:
                        buf.popleft()
                    elif playback_started:
                        underruns += 1
                        if underruns % 5 == 1:
                            print(f"  [spk-recv] UNDERRUN #{underruns} — buffer empty, silence gap!")
                        stats.record_drop()

        except (ConnectionError, OSError) as e:
            print(f"[spk-recv] disconnected: {e}")
            stats.record_error()
        finally:
            sock.close()
            if underruns > 0:
                print(f"[spk-recv] total underruns this connection: {underruns}")


def run_simulation(jitter_ms: int, duration: int):
    print(f"\n{'='*60}")
    print(f"  Network Audio Simulation")
    print(f"  Jitter: {jitter_ms}ms | Duration: {duration}s")
    print(f"  Mic: 127.0.0.1:{MIC_PORT} | Speaker: 127.0.0.1:{SPK_PORT}")
    print(f"{'='*60}\n")

    stop = threading.Event()

    mic_srv_stats = Stats("pi-mic-srv")
    spk_srv_stats = Stats("pi-spk-srv")
    mic_send_stats = Stats("mac-mic-send")
    spk_recv_stats = Stats("mac-spk-recv")

    threads = [
        threading.Thread(target=fake_pi_mic_server, args=(MIC_PORT, jitter_ms, stop, mic_srv_stats), daemon=True),
        threading.Thread(target=fake_pi_speaker_server, args=(SPK_PORT, jitter_ms, stop, spk_srv_stats), daemon=True),
        threading.Thread(target=mic_sender_under_test, args=("127.0.0.1", MIC_PORT, stop, mic_send_stats), daemon=True),
        threading.Thread(target=speaker_receiver_under_test, args=("127.0.0.1", SPK_PORT, stop, spk_recv_stats), daemon=True),
    ]

    for t in threads:
        t.start()

    # Let connections establish
    time.sleep(1)

    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            time.sleep(5)
            elapsed = time.monotonic() - t0
            print(f"\n--- {elapsed:.0f}s / {duration}s ---")
            print(mic_srv_stats.report())
            print(spk_srv_stats.report())
            print(mic_send_stats.report())
            print(spk_recv_stats.report())
    except KeyboardInterrupt:
        pass

    print(f"\n{'='*60}")
    print("  FINAL SUMMARY")
    print(f"{'='*60}")
    print(mic_srv_stats.report())
    print(spk_srv_stats.report())
    print(mic_send_stats.report())
    print(spk_recv_stats.report())

    stop.set()
    time.sleep(1)

    # Verdict
    total_errors = (
        mic_srv_stats.errors + spk_srv_stats.errors
        + mic_send_stats.errors + spk_recv_stats.errors
    )
    total_drops = mic_send_stats.drops + spk_recv_stats.drops
    print(f"\n  Errors: {total_errors} | Drops: {total_drops}")
    if total_errors > 0 or total_drops > 5:
        print("  VERDICT: FAIL — audio would cut off / crash under these conditions")
        return 1
    else:
        print("  VERDICT: PASS — stream stable")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Simulate Pi↔Mac network audio")
    parser.add_argument("--jitter", type=int, default=0, help="Max jitter in ms (0=clean, 50=mild, 200=bad WiFi)")
    parser.add_argument("--duration", type=int, default=15, help="Test duration in seconds")
    args = parser.parse_args()
    sys.exit(run_simulation(args.jitter, args.duration))


if __name__ == "__main__":
    main()
