"""Mac-side mic sender — streams raw 16kHz mono 16-bit PCM over TCP to the Pi.
Auto-reconnects if the connection drops.

Usage:
    python scripts/mac_mic_sender.py <PI_HOST> [PORT]

Requires: pip install sounddevice numpy scipy
"""

import sys
import socket
import time
import threading
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
from math import gcd

TARGET_RATE = 16000
BLOCK_MS = 100
DEFAULT_PORT = 9999

# --- logging stats ---
_send_lock = threading.Lock()
_send_count = 0
_send_bytes = 0
_send_errors = 0
_send_rms_sum = 0
_send_rms_peak = 0
_send_t0 = time.monotonic()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <PI_HOST> [PORT]")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

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
            print("Connected — streaming mic audio")
        except (ConnectionRefusedError, OSError) as e:
            print(f"Can't connect: {e} — retrying in 2s...")
            sock.close()
            time.sleep(2)
            continue

        broken = threading.Event()

        def callback(indata, frames, time_info, status):
            global _send_count, _send_bytes, _send_errors, _send_rms_sum, _send_rms_peak, _send_t0
            if broken.is_set():
                raise sd.CallbackAbort
            if status:
                print(f"  sounddevice: {status}", file=sys.stderr)
            samples = indata[:, 0].astype(np.float32)
            # RMS of raw input
            rms = int(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
            if hw_rate != TARGET_RATE:
                samples = resample_poly(samples, up, down)
            pcm = samples.astype(np.int16).tobytes()
            try:
                sock.sendall(pcm)
                with _send_lock:
                    _send_count += 1
                    _send_bytes += len(pcm)
                    _send_rms_sum += rms
                    if rms > _send_rms_peak:
                        _send_rms_peak = rms
                    now = time.monotonic()
                    if now - _send_t0 >= 5.0:
                        elapsed = now - _send_t0
                        avg_rms = _send_rms_sum // max(_send_count, 1)
                        print(
                            f"  [stats] sent={_send_count} ({_send_count/elapsed:.1f}/s) "
                            f"bytes={_send_bytes} rms_avg={avg_rms} rms_peak={_send_rms_peak} "
                            f"errors={_send_errors} pcm_len={len(pcm)}"
                        )
                        _send_count = 0
                        _send_bytes = 0
                        _send_errors = 0
                        _send_rms_sum = 0
                        _send_rms_peak = 0
                        _send_t0 = now
            except (BrokenPipeError, OSError):
                with _send_lock:
                    _send_errors += 1
                broken.set()
                raise sd.CallbackAbort

        try:
            with sd.InputStream(samplerate=hw_rate, channels=1, dtype="int16",
                                blocksize=hw_block, callback=callback):
                broken.wait()
            print("Connection lost — reconnecting...")
            time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")
            sock.close()
            return
        finally:
            sock.close()


if __name__ == "__main__":
    main()
