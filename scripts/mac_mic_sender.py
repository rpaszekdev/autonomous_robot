"""Mac-side mic sender — streams raw 16kHz mono 16-bit PCM over TCP to the Pi.
Auto-reconnects if the connection drops.

The audio callback only enqueues PCM into a thread-safe queue — a background
sender thread does the actual socket I/O. This prevents WiFi stalls from
blocking the real-time audio callback and crashing the stream.

Usage:
    python scripts/mac_mic_sender.py <PI_HOST> [PORT]

Requires: pip install sounddevice numpy scipy
"""

import sys
import socket
import time
import threading
import queue
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
from math import gcd

TARGET_RATE = 16000
BLOCK_MS = 100
DEFAULT_PORT = 9999
SEND_QUEUE_MAX = 50

_lock = threading.Lock()
_stats = {
    "sent": 0, "bytes": 0, "queued": 0, "dropped": 0,
    "rms_sum": 0, "rms_peak": 0, "t0": time.monotonic(),
}


def _reset_stats():
    _stats["sent"] = 0
    _stats["bytes"] = 0
    _stats["queued"] = 0
    _stats["dropped"] = 0
    _stats["rms_sum"] = 0
    _stats["rms_peak"] = 0
    _stats["t0"] = time.monotonic()


def _log_stats(send_q: queue.Queue):
    now = time.monotonic()
    with _lock:
        if now - _stats["t0"] < 5.0:
            return
        elapsed = now - _stats["t0"]
        avg_rms = _stats["rms_sum"] // max(_stats["queued"], 1)
        print(
            f"  [stats] queued={_stats['queued']} sent={_stats['sent']} "
            f"({_stats['sent']/elapsed:.1f}/s) bytes={_stats['bytes']} "
            f"rms_avg={avg_rms} rms_peak={_stats['rms_peak']} "
            f"dropped={_stats['dropped']} qsize={send_q.qsize()}"
        )
        _reset_stats()


def _sender_thread(sock: socket.socket, send_q: queue.Queue, broken: threading.Event):
    while not broken.is_set():
        try:
            pcm = send_q.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            sock.sendall(pcm)
            with _lock:
                _stats["sent"] += 1
                _stats["bytes"] += len(pcm)
            _log_stats(send_q)
        except (BrokenPipeError, OSError):
            broken.set()
            return


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <PI_HOST> [PORT]")
        print(f"\nExamples:")
        print(f"  python {sys.argv[0]} raspberrypi.local")
        print(f"  python {sys.argv[0]} 172.20.10.5")
        print(f"  python {sys.argv[0]} 192.168.1.100 9999")
        print(f"\nNote: Use IP address if 'raspberrypi.local' fails (e.g., on eduroam).")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    
    # Provide helpful hints for common issues
    if host == "raspberrypi.local":
        print(f"Attempting to connect to {host}:{port}...")
        print(f"Hint: If this fails, try with IP address instead (e.g., 172.20.10.5)")

    dev_info = sd.query_devices(kind="input")
    hw_rate = int(dev_info["default_samplerate"])
    hw_block = int(hw_rate * BLOCK_MS / 1000)
    print(f"Mic: {dev_info['name']} @ {hw_rate} Hz")

    g = gcd(TARGET_RATE, hw_rate)
    up, down = TARGET_RATE // g, hw_rate // g

    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            print(f"Connecting to {host}:{port}...")
            sock.connect((host, port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print("Connected — streaming mic audio")
        except (ConnectionRefusedError, OSError, socket.gaierror) as e:
            print(f"Can't connect to {host}:{port}: {e}")
            if host == "raspberrypi.local":
                print(f"  Hint: mDNS resolution failed (common on eduroam).")
                print(f"  Try using IP address: python {sys.argv[0]} <PI_IP_ADDRESS>")
            print(f"  Retrying in 2s...")
            sock.close()
            time.sleep(2)
            continue

        broken = threading.Event()
        send_q = queue.Queue(maxsize=SEND_QUEUE_MAX)
        _reset_stats()

        sender = threading.Thread(
            target=_sender_thread, args=(sock, send_q, broken), daemon=True
        )
        sender.start()

        def callback(indata, frames, time_info, status):
            if broken.is_set():
                raise sd.CallbackAbort
            if status:
                print(f"  sounddevice: {status}", file=sys.stderr)
            samples = indata[:, 0].astype(np.float32)
            rms = int(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
            if hw_rate != TARGET_RATE:
                samples = resample_poly(samples, up, down)
            pcm = np.clip(samples, -32768, 32767).astype(np.int16).tobytes()
            try:
                send_q.put_nowait(pcm)
                with _lock:
                    _stats["queued"] += 1
                    _stats["rms_sum"] += rms
                    if rms > _stats["rms_peak"]:
                        _stats["rms_peak"] = rms
            except queue.Full:
                with _lock:
                    _stats["dropped"] += 1
                if _stats["dropped"] % 10 == 1:
                    print(f"  [warn] send queue full, dropped frame (total={_stats['dropped']})")

        try:
            with sd.InputStream(samplerate=hw_rate, channels=1, dtype="int16",
                                blocksize=hw_block, callback=callback):
                broken.wait()
            print("Connection lost — reconnecting...")
            time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")
            broken.set()
            sock.close()
            return
        finally:
            broken.set()
            sock.close()


if __name__ == "__main__":
    main()
