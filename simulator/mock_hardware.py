"""Hardware mocks for testing on non-Pi machines (Windows/Mac/Linux desktop).

Replaces: picamera2, gpiozero, RPi.GPIO, aplay
Simulates: camera (returns test image), motors (logs to console), audio (uses default mic)
"""

import logging
import base64
import io
import os

logger = logging.getLogger(__name__)


class MockCamera:
    """Returns a small test JPEG instead of a real camera capture."""

    def __init__(self):
        logger.info("[SIM] Camera initialised (mock — no real camera)")

    def capture_jpeg(self) -> bytes:
        # Generate a tiny 1x1 red JPEG as placeholder
        try:
            from PIL import Image
            img = Image.new("RGB", (640, 480), color=(100, 120, 200))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            logger.info("[SIM] Mock camera snapshot captured")
            return buf.getvalue()
        except ImportError:
            # Minimal valid JPEG if Pillow not available
            logger.info("[SIM] Mock camera snapshot (no Pillow)")
            return b'\xff\xd8\xff\xe0' + b'\x00' * 100 + b'\xff\xd9'

    def capture_base64(self) -> str:
        return base64.b64encode(self.capture_jpeg()).decode("ascii")

    def close(self):
        logger.info("[SIM] Camera closed")


class MockMotor:
    """Logs motor commands instead of driving GPIO pins."""

    def __init__(self, name="motor"):
        self.name = name

    def forward(self, speed=0.5):
        logger.info("[SIM] %s → FORWARD (speed=%.1f)", self.name, speed)

    def backward(self, speed=0.5):
        logger.info("[SIM] %s → BACKWARD (speed=%.1f)", self.name, speed)

    def stop(self):
        logger.info("[SIM] %s → STOP", self.name)


class MockRobot:
    """Simulates gpiozero.Robot for wheel control."""

    def __init__(self, left=None, right=None):
        self.left = MockMotor("left_wheel")
        self.right = MockMotor("right_wheel")
        logger.info("[SIM] Robot motors initialised (mock)")

    def forward(self, speed=0.5):
        logger.info("[SIM] 🚗 Moving FORWARD (speed=%.1f)", speed)

    def backward(self, speed=0.5):
        logger.info("[SIM] 🚗 Moving BACKWARD (speed=%.1f)", speed)

    def left(self, speed=0.5):
        logger.info("[SIM] 🚗 Turning LEFT (speed=%.1f)", speed)

    def right(self, speed=0.5):
        logger.info("[SIM] 🚗 Turning RIGHT (speed=%.1f)", speed)

    def stop(self):
        logger.info("[SIM] 🚗 STOPPED")


class MockLED:
    """Simulates gpiozero.LED."""

    def __init__(self, pin):
        self.pin = pin
        logger.info("[SIM] LED on pin %d (mock)", pin)

    def on(self):
        logger.info("[SIM] 💡 Pin %d → HIGH", self.pin)

    def off(self):
        logger.info("[SIM] 💡 Pin %d → LOW", self.pin)

    def close(self):
        pass


class MockTTS:
    """Prints speech to console instead of running Piper + aplay."""

    def __init__(self, **kwargs):
        logger.info("[SIM] TTS initialised (console output)")

    def speak(self, text: str, speed: float = 1.0):
        print(f"\n🔊 ROBOT SAYS: {text}\n")

    def speak_async(self, text: str, speed: float = 1.0):
        print(f"\n🔊 ROBOT SAYS: {text}\n")

    def stop(self):
        pass


class MockWakeWord:
    """Skips wake word — uses keyboard Enter key as trigger."""

    def __init__(self, on_wake=None, **kwargs):
        self.on_wake = on_wake
        self._running = False
        logger.info("[SIM] Wake word replaced with keyboard trigger (press Enter)")

    def start(self):
        import threading
        self._running = True
        self._thread = threading.Thread(target=self._keyboard_loop, daemon=True)
        self._thread.start()

    def _keyboard_loop(self):
        while self._running:
            try:
                input("\n⏎  Press ENTER to simulate wake word ('Hey Robot')...\n")
                if self.on_wake:
                    logger.info("[SIM] Wake word triggered via keyboard")
                    self.on_wake()
            except EOFError:
                break

    def stop(self):
        self._running = False


class MockAudioCapture:
    """Records from default microphone, or prompts for text input if no mic."""

    def __init__(self):
        self._has_mic = False
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            if pa.get_device_count() > 0:
                self._has_mic = True
            pa.terminate()
        except Exception:
            pass

        if self._has_mic:
            logger.info("[SIM] Audio capture using default microphone")
        else:
            logger.info("[SIM] No microphone — using text input instead")

    def record_until_silence(self) -> bytes:
        if self._has_mic:
            # Use real audio capture
            from perception.audio_capture import AudioCapture
            real = AudioCapture()
            return real.record_until_silence()
        else:
            # Fall back to text input (encode as raw bytes for the pipeline)
            text = input("🎤 Type what you'd say: ")
            # Return text encoded as PCM-like bytes (the LLM will receive it as audio)
            return text.encode("utf-8")
