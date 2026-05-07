#!/usr/bin/env python3
"""Stream robot audio from Pi TCP port 9001 and play on Mac speakers.
Auto-reconnects. Buffers to smooth network jitter.
"""
import socket
import struct
import time
import threading
import collections
import sounddevice as sd
import numpy as np

PI_HOST = "raspberrypi.local"
PI_PORT = 9001
SAMPLE_RATE = 24000
CHANNELS = 1
FRAME_SIZE = 2400          # 100ms @ 24kHz for sounddevice callback
PRE_BUFFER_FRAMES = 8     # buffer 800ms before starting playback to absorb WiFi jitter


def stream_once():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((PI_HOST, PI_PORT))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print(f"Connected to {PI_HOST}:{PI_PORT}")

    buf = collections.deque()
    lock = threading.Lock()
    started = threading.Event()
    done = threading.Event()

    # --- logging stats ---
    stats = {
        "recv_count": 0, "recv_bytes": 0, "frames_queued": 0,
        "underruns": 0, "oversize": 0, "timeouts": 0,
        "cb_calls": 0, "cb_silence": 0, "t0": time.monotonic(),
    }

    def audio_callback(outdata, frames, time_info, status):
        needed = frames * 2
        stats["cb_calls"] += 1
        if status:
            print(f"  [playback] status: {status}")
        with lock:
            if buf:
                data = buf.popleft()
                # Pad or trim to exact size
                if len(data) < needed:
                    data += b"\x00" * (needed - len(data))
                elif len(data) > needed:
                    buf.appendleft(data[needed:])
                    data = data[:needed]
                outdata[:] = np.frombuffer(data, dtype=np.int16).reshape(-1, 1)
            else:
                outdata[:] = np.zeros((frames, 1), dtype=np.int16)
                stats["cb_silence"] += 1

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=FRAME_SIZE,
        callback=audio_callback,
    )

    pre_buffered = 0

    def recv_exact(n):
        """Read exactly n bytes from sock, or raise ConnectionError."""
        parts = []
        remaining = n
        while remaining > 0:
            try:
                chunk = sock.recv(remaining)
            except socket.timeout:
                stats["timeouts"] += 1
                continue
            if not chunk:
                raise ConnectionError("EOF from server")
            parts.append(chunk)
            remaining -= len(chunk)
        return b"".join(parts)

    try:
        while not done.is_set():
            # Read 4-byte length header
            header = recv_exact(4)
            msg_len = struct.unpack(">I", header)[0]
            # Read the PCM payload
            pcm = recv_exact(msg_len)

            stats["recv_count"] += 1
            stats["recv_bytes"] += msg_len
            with lock:
                buf.append(pcm)
                stats["frames_queued"] += 1
            if not started.is_set():
                pre_buffered += 1
                if pre_buffered >= PRE_BUFFER_FRAMES:
                    print(f"  [playback] pre-buffer filled, starting playback")
                    stream.start()
                    started.set()

            # Log stats every 5 seconds
            now = time.monotonic()
            if now - stats["t0"] >= 5.0:
                elapsed = now - stats["t0"]
                with lock:
                    buflen = len(buf)
                rms_str = ""
                if stats["frames_queued"] > 0:
                    try:
                        samples = np.frombuffer(pcm, dtype=np.int16)
                        rms = int(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                        rms_str = f" rms={rms}"
                    except Exception:
                        pass
                print(
                    f"  [stats] recv={stats['recv_count']} ({stats['recv_count']/elapsed:.1f}/s) "
                    f"bytes={stats['recv_bytes']} frames_queued={stats['frames_queued']} "
                    f"buf_depth={buflen} cb_calls={stats['cb_calls']} "
                    f"silence={stats['cb_silence']} timeouts={stats['timeouts']}"
                    f"{rms_str}"
                )
                stats["recv_count"] = 0
                stats["recv_bytes"] = 0
                stats["frames_queued"] = 0
                stats["cb_calls"] = 0
                stats["cb_silence"] = 0
                stats["timeouts"] = 0
                stats["t0"] = now
    finally:
        # Drain remaining audio
        if started.is_set():
            with lock:
                remaining = len(buf)
            print(f"  [drain] draining {remaining} buffered frames...")
            while True:
                with lock:
                    empty = len(buf) == 0
                if empty:
                    break
                time.sleep(0.05)
            time.sleep(0.2)
        stream.stop()
        stream.close()
        sock.close()


def main():
    print("Streaming robot audio to Mac speakers... (Ctrl+C to stop)")
    while True:
        try:
            stream_once()
            print("Audio stream ended — reconnecting...")
            time.sleep(0.5)
        except ConnectionRefusedError:
            print("Robot not ready — retrying in 2s...")
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"Error: {e} — retrying in 1s")
            time.sleep(1)


if __name__ == "__main__":
    main()
