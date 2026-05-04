#!/usr/bin/env python3
"""Stream robot audio from Pi TCP port 9001 and play on Mac speakers.
Auto-reconnects. Buffers to smooth network jitter.
"""
import socket
import time
import threading
import collections
import sounddevice as sd
import numpy as np

PI_HOST = "raspberrypi.local"
PI_PORT = 9001
SAMPLE_RATE = 24000
CHANNELS = 1
FRAME_SIZE = 2400          # 100ms @ 24kHz
FRAME_BYTES = FRAME_SIZE * 2  # 16-bit
PRE_BUFFER_FRAMES = 3     # buffer 300ms before starting playback


def stream_once():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((PI_HOST, PI_PORT))
    print(f"Connected to {PI_HOST}:{PI_PORT}")

    buf = collections.deque()
    lock = threading.Lock()
    started = threading.Event()
    done = threading.Event()

    def audio_callback(outdata, frames, time_info, status):
        needed = frames * 2
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

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=FRAME_SIZE,
        callback=audio_callback,
    )

    leftover = b""
    pre_buffered = 0

    try:
        while not done.is_set():
            try:
                chunk = sock.recv(8192)
            except socket.timeout:
                continue
            if not chunk:
                break

            leftover += chunk
            # Chop into aligned frames
            while len(leftover) >= FRAME_BYTES:
                frame = leftover[:FRAME_BYTES]
                leftover = leftover[FRAME_BYTES:]
                with lock:
                    buf.append(frame)
                if not started.is_set():
                    pre_buffered += 1
                    if pre_buffered >= PRE_BUFFER_FRAMES:
                        stream.start()
                        started.set()
    finally:
        # Drain remaining audio
        if started.is_set():
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
