"""set_reminder tool — Schedules a future speak() via threading timer."""

import threading
import logging

logger = logging.getLogger(__name__)

_tts_instance = None


def set_tts(tts):
    global _tts_instance
    _tts_instance = tts


def tool_set_reminder(message: str, delay_seconds: int, **kwargs) -> dict:
    """Schedule the robot to speak a message after a delay."""
    def _fire():
        logger.info("Reminder firing: %s", message)
        if _tts_instance:
            _tts_instance.speak(f"Reminder: {message}")

    timer = threading.Timer(delay_seconds, _fire)
    timer.daemon = True
    timer.start()
    logger.info("Reminder set: '%s' in %ds", message, delay_seconds)
    return {"status": "ok", "message": message, "delay_seconds": delay_seconds}
