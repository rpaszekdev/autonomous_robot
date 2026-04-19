"""Diagnostic tests for the 'mic dead after turn 1' bug.

Each test maps to one of three hypotheses. The ones that fail identify
the real cause(s).

  Cause 1: ActivityHandling.NO_INTERRUPTION in the Live config wedges the
           server so follow-up user turns get no response.
  Cause 2: Mic is unmuted the instant turn_complete arrives, while the
           SpeakerStream buffer still has Gemini's tail playing — that tail
           leaks back into the hot mic.
  Cause 3: set_muted(False) drains the mic queue on unmute, discarding any
           PCM that arrived in the last tick right before transition.
"""

from __future__ import annotations

import asyncio

import pytest
from google.genai import types

from robot.live.audio_io import MicStream
from robot.live.session import GeminiLiveSession


# --- Cause 1 --------------------------------------------------------------

def test_cause1_live_config_does_not_block_followup_turns():
    """NO_INTERRUPTION + automatic VAD makes the server drop audio received
    while it's still considered 'responding'. After turn_complete the server
    often doesn't cleanly reopen activity detection for subsequent turns —
    so the client happily streams mic audio and gets silence back.

    Safe default is START_OF_ACTIVITY_INTERRUPTS (or just omit the field).
    """
    session = GeminiLiveSession(
        api_key="test",
        model="gemini-test",
        system_instruction="x",
        tools=[],
        on_audio_out=lambda b: None,  # type: ignore[arg-type]
        on_tool_call=lambda n, a: None,  # type: ignore[arg-type]
    )
    cfg = session._config
    rt = cfg.realtime_input_config
    ah = getattr(rt, "activity_handling", None) if rt is not None else None
    assert ah != types.ActivityHandling.NO_INTERRUPTION, (
        "NO_INTERRUPTION blocks follow-up user turns once Gemini has "
        "responded. Drop the activity_handling override (or use "
        "START_OF_ACTIVITY_INTERRUPTS)."
    )


# --- Cause 2 --------------------------------------------------------------
# The real symptom is acoustic — speaker tail leaking into the mic — which
# unit tests can't observe directly. What we CAN check is whether the code
# gives the speaker any grace period before re-hotting the mic. The current
# runtime flips mic → listening synchronously on turn_complete (see
# runtime.py `on_state_change`), with zero delay. We assert a
# post-gemini_speaking hold exists. If this test fails, cause 2 is live.


def test_cause2_post_speaking_mic_hold_is_configured():
    """After gemini_speaking → listening, the mic should stay muted for a
    short grace period so the speaker tail can drain. We detect this by
    looking for a hold constant or a sleep in the runtime module."""
    import inspect

    from robot import runtime

    src = inspect.getsource(runtime)
    hints = (
        "POST_SPEAK_MUTE",  # an explicit constant
        "asyncio.sleep",    # or a delayed unmute
        "speaker.drain",    # or waiting on the buffer
    )
    assert any(h in src for h in hints), (
        "runtime.py unmutes the mic the instant turn_complete fires. "
        "The speaker buffer is still playing Gemini's tail — that audio "
        "feeds straight back into the mic and confuses server VAD."
    )


# --- Cause 3 --------------------------------------------------------------

@pytest.mark.asyncio
async def test_cause3_unmute_does_not_discard_queued_audio():
    """set_muted(False) used to call _drain_queue() on the unmute
    transition too, throwing away the first chunk of the user's reply."""
    received: list[bytes] = []

    async def sink(chunk: bytes) -> None:
        received.append(chunk)

    mic = MicStream(sink, device=None)
    mic.set_muted(True)
    mic._queue.put_nowait(b"user-syllable")  # arrived mid-transition
    mic.set_muted(False)

    mic._running = True
    pump = asyncio.create_task(mic.pump())
    await asyncio.sleep(0.05)
    mic._running = False
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass

    assert received == [b"user-syllable"]


@pytest.mark.asyncio
async def test_cause4_mute_pauses_stream_and_fires_audio_stream_end():
    """On the mute transition, pump must:
      1. drop subsequent mic frames (actually pause, not silence-stream)
      2. fire the on_mute_flush callback exactly once
    Per Gemini Live docs: pauses >1s require audio_stream_end to flush the
    server's automatic VAD, otherwise next turn never gets a response."""
    received: list[bytes] = []
    flushes: list[None] = []

    async def sink(chunk: bytes) -> None:
        received.append(chunk)

    async def flush() -> None:
        flushes.append(None)

    mic = MicStream(sink, device=None, on_mute_flush=flush)
    mic._running = True
    pump = asyncio.create_task(mic.pump())

    # Phase 1: unmuted real voice passes through.
    mic._queue.put_nowait(b"\x11\x22" * 10)
    await asyncio.sleep(0.02)

    # Phase 2: muted — frames are dropped, flush fires exactly once.
    mic.set_muted(True)
    mic._queue.put_nowait(b"\x33\x44" * 10)  # dropped
    mic._queue.put_nowait(b"\x33\x44" * 10)  # dropped, flush must not re-fire
    await asyncio.sleep(0.02)

    # Phase 3: unmute — real voice passes through.
    mic.set_muted(False)
    mic._queue.put_nowait(b"\x55\x66" * 10)
    await asyncio.sleep(0.02)

    mic._running = False
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass

    assert received == [b"\x11\x22" * 10, b"\x55\x66" * 10], (
        f"muted frames must be dropped, not forwarded: {received}"
    )
    assert len(flushes) == 1, (
        f"audio_stream_end must fire exactly once per mute transition, "
        f"got {len(flushes)}"
    )
