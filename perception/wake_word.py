"""Wake word detection using openWakeWord.

Runs on a dedicated background thread. Listens for 'Hey Robot'.
On detection: fires callback to start the agent loop.
"""

import threading
import logging
import numpy as np
import pyaudio
from openwakeword.model import Model

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1280          # ~80ms at 16kHz
SAMPLE_RATE = 16000
THRESHOLD = 0.7
WAKE_WORD = "hey_jarvis"   # closest built-in model; swap for custom .onnx


CHUNK_BYTES = CHUNK_SIZE * 2  # 16-bit = 2 bytes per sample


class WakeWordDetector:
    def __init__(self, model_path: str | None = None, on_wake=None,
                 network_stream=None):
        """
        Args:
            network_stream: Optional NetworkAudioStream instance.
                            If provided, reads audio from TCP instead of local mic.
        """
        self.on_wake = on_wake
        self._running = False
        self._net = network_stream

        # Load openWakeWord model
        kwargs = {}
        if model_path:
            kwargs["wakeword_models"] = [model_path]
        self.model = Model(**kwargs)
        logger.info("Wake word model loaded (threshold=%.2f)", THRESHOLD)

    def _audio_loop(self):
        pa = None
        stream = None
        if not self._net:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
        logger.info("Wake word listener active")

        try:
            while self._running:
                if self._net:
                    pcm = self._net.read(CHUNK_BYTES)
                else:
                    pcm = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                audio = np.frombuffer(pcm, dtype=np.int16)
                prediction = self.model.predict(audio)

                for wake_name, score in prediction.items():
                    if score >= THRESHOLD:
                        logger.info("Wake word detected: %s (%.2f)", wake_name, score)
                        self.model.reset()
                        if self.on_wake:
                            self.on_wake()
                        break
        finally:
            if pa:
                stream.stop_stream()
                stream.close()
                pa.terminate()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2.0)
