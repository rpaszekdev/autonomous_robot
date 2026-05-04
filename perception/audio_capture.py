"""Audio capture with Voice Activity Detection (VAD).

USB microphone via PyAudio. Recording is terminated by silence detection
using webrtcvad. Returns raw 16kHz mono PCM bytes.
"""

import logging
import webrtcvad
import pyaudio
import collections

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30        # webrtcvad supports 10, 20, 30 ms
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples
MAX_RECORD_SECONDS = 10
SILENCE_TIMEOUT_MS = 1200     # stop after 1.2s of silence
VAD_AGGRESSIVENESS = 2        # 0-3, higher = more aggressive filtering


FRAME_BYTES = FRAME_SIZE * 2  # 16-bit = 2 bytes per sample


class AudioCapture:
    def __init__(self, network_stream=None):
        """
        Args:
            network_stream: Optional NetworkAudioStream instance.
                            If provided, reads audio from TCP instead of local mic.
        """
        self.vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        self._net = network_stream

    def _read_frame(self, stream):
        """Read one VAD frame from either PyAudio or network stream."""
        if self._net:
            return self._net.read(FRAME_BYTES)
        return stream.read(FRAME_SIZE, exception_on_overflow=False)

    def record_until_silence(self) -> bytes:
        """Record from microphone (or network) until the user stops speaking.

        Returns:
            Raw 16kHz mono 16-bit PCM bytes.
        """
        pa = None
        stream = None
        if not self._net:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=FRAME_SIZE,
            )

        frames: list[bytes] = []
        num_silence_frames = 0
        silence_limit = int(SILENCE_TIMEOUT_MS / FRAME_DURATION_MS)
        max_frames = int(MAX_RECORD_SECONDS * 1000 / FRAME_DURATION_MS)
        speech_started = False

        # Ring buffer to hold pre-speech frames
        ring_buffer = collections.deque(maxlen=10)

        logger.info("Recording...")
        try:
            for _ in range(max_frames):
                pcm = self._read_frame(stream)
                is_speech = self.vad.is_speech(pcm, SAMPLE_RATE)

                if not speech_started:
                    ring_buffer.append(pcm)
                    if is_speech:
                        speech_started = True
                        frames.extend(ring_buffer)
                        ring_buffer.clear()
                else:
                    frames.append(pcm)
                    if not is_speech:
                        num_silence_frames += 1
                        if num_silence_frames >= silence_limit:
                            break
                    else:
                        num_silence_frames = 0
        finally:
            if pa:
                stream.stop_stream()
                stream.close()
                pa.terminate()

        logger.info("Recorded %d frames (%.1fs)", len(frames),
                     len(frames) * FRAME_DURATION_MS / 1000)
        return b"".join(frames)
