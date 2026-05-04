"""OpenClaw — Main daemon entry point.

Starts all subsystems:
  1. llama.cpp health check
  2. Wake word detector (background thread)
  3. Agent event loop (main thread)
"""

import sys
import os
import signal
import logging
import time
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perception.wake_word import WakeWordDetector
from perception.audio_capture import AudioCapture
from perception.camera import Camera
from perception.network_audio import NetworkAudioStream
from openclaw.event_loop import EventLoop
from openclaw.prompt_builder import PromptBuilder
from openclaw.tool_parser import ToolParser
from tts.piper_stream import PiperTTS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("openclaw")

# ── Configuration ────────────────────────────────────────────
ROBOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(ROBOT_DIR, "models", "gemma-4-e4b-it-q4_k_m.gguf")
LLAMA_URL = "http://127.0.0.1:8080"
ACK_TONE = os.path.join(ROBOT_DIR, "assets", "ack_tone.wav")
SYSTEM_PROMPT_PATH = os.path.join(ROBOT_DIR, "robot_system_prompt.txt")
MEMORY_PATH = os.path.join(ROBOT_DIR, "memory.json")


def wait_for_llama(url: str, timeout: int = 60):
    """Block until llama.cpp server is responsive."""
    import requests
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                logger.info("llama.cpp server is ready")
                return
        except requests.ConnectionError:
            pass
        time.sleep(1)
    raise RuntimeError(f"llama.cpp server not ready after {timeout}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network-audio", type=int, nargs="?", const=9999,
                        metavar="PORT",
                        help="Receive mic audio over TCP (default port 9999)")
    args = parser.parse_args()

    logger.info("═══ Conversational Robot starting ═══")

    # Check llama.cpp server
    wait_for_llama(LLAMA_URL)

    # Optionally set up network audio (mic streamed from Mac)
    net_stream = None
    if args.network_audio:
        net_stream = NetworkAudioStream(port=args.network_audio)
        net_stream.wait_for_connection()

    # Initialise subsystems
    audio_capture = AudioCapture(network_stream=net_stream)
    camera = Camera()
    tts = PiperTTS(
        piper_binary=os.path.join(ROBOT_DIR, "piper", "piper"),
        voice_model=os.path.join(ROBOT_DIR, "models", "piper-voices", "en_US-lessac-medium.onnx"),
    )
    prompt_builder = PromptBuilder(
        system_prompt_path=SYSTEM_PROMPT_PATH,
        memory_path=MEMORY_PATH,
    )
    tool_parser = ToolParser()

    # Create event loop
    event_loop = EventLoop(
        llama_url=LLAMA_URL,
        audio_capture=audio_capture,
        camera=camera,
        tts=tts,
        prompt_builder=prompt_builder,
        tool_parser=tool_parser,
        ack_tone_path=ACK_TONE,
    )

    # Wire up wake word → event loop
    wake = WakeWordDetector(on_wake=event_loop.on_wake_word,
                            network_stream=net_stream)
    wake.start()

    logger.info("═══ Robot ready — listening for wake word ═══")

    # Graceful shutdown
    def shutdown(sig, frame):
        logger.info("Shutting down...")
        wake.stop()
        camera.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
