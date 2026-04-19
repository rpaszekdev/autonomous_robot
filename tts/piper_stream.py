"""Piper TTS — Streaming speech synthesis.

Receives text sentence-by-sentence from OpenClaw.
Synthesises audio chunks, pipes to aplay → speakers.
First audio out within ~150ms of first sentence.
"""

import subprocess
import logging
import threading
import queue
import os

logger = logging.getLogger(__name__)


class PiperTTS:
    def __init__(self, piper_binary: str, voice_model: str):
        self.piper_binary = piper_binary
        self.voice_model = voice_model
        self._queue = queue.Queue()
        self._running = True

        # Background worker for sequential speech
        self._worker = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker.start()

    def _speech_worker(self):
        """Process speech requests sequentially."""
        while self._running:
            try:
                text, speed = self._queue.get(timeout=1.0)
                self._synthesise_and_play(text, speed)
                self._queue.task_done()
            except queue.Empty:
                continue

    def _synthesise_and_play(self, text: str, speed: float = 1.0):
        """Run Piper → aplay pipeline for a chunk of text."""
        if not text.strip():
            return

        cmd = [
            self.piper_binary,
            "--model", self.voice_model,
            "--output-raw",
        ]

        if speed != 1.0:
            cmd.extend(["--length-scale", str(1.0 / speed)])

        try:
            # Piper outputs raw 16-bit 22050Hz mono PCM → pipe to aplay
            piper_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            aplay_proc = subprocess.Popen(
                ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-q"],
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            piper_proc.stdin.write(text.encode("utf-8"))
            piper_proc.stdin.close()

            piper_proc.wait(timeout=10)
            aplay_proc.wait(timeout=10)

            logger.debug("Spoke: %s", text[:60])

        except subprocess.TimeoutExpired:
            logger.warning("TTS timeout for: %s", text[:40])
            piper_proc.kill()
            aplay_proc.kill()
        except FileNotFoundError:
            logger.error("Piper or aplay binary not found")
        except Exception as e:
            logger.error("TTS error: %s", e)

    def speak(self, text: str, speed: float = 1.0):
        """Speak text synchronously (blocks until done)."""
        self._synthesise_and_play(text, speed)

    def speak_async(self, text: str, speed: float = 1.0):
        """Queue text for background speech (non-blocking)."""
        self._queue.put((text, speed))

    def stop(self):
        self._running = False
