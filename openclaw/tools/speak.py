"""speak tool — Routes text to Piper TTS."""

import logging

logger = logging.getLogger(__name__)

# TTS instance is injected at runtime via the event loop.
# This module provides the tool interface for the tool parser.
_tts_instance = None


def set_tts(tts):
    global _tts_instance
    _tts_instance = tts


def tool_speak(text: str, speed: float = 1.0, **kwargs) -> dict:
    """Speak text aloud through Piper TTS."""
    logger.info("speak: %s", text[:80])
    if _tts_instance:
        _tts_instance.speak(text, speed=speed)
    return {"status": "ok", "spoken": text}
