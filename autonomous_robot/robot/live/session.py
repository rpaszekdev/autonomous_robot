"""Gemini Live WebSocket session wrapper.

Thin, async context-manager around google-genai's live API. Owns:
  - sending realtime audio frames + image blobs
  - receiving audio chunks and dispatching them to a playback callback
  - receiving tool_calls and posting tool_responses
"""

from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable

import time
from typing import Callable

from google import genai
from google.genai import types

from robot import ui

logger = logging.getLogger(__name__)

DEBUG_LIVE = os.environ.get("DEBUG_LIVE", "1") == "1"

AudioOut = Callable[[bytes], Awaitable[None]]
ToolCallHandler = Callable[[str, dict], Awaitable[dict]]


class GeminiLiveSession:
    def __init__(
        self,
        api_key: str,
        model: str,
        system_instruction: str,
        tools: list[types.FunctionDeclaration],
        on_audio_out: AudioOut,
        on_tool_call: ToolCallHandler,
        on_state_change: "Callable[[str], None] | None" = None,
        resumption_handle: "str | None" = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        # Enable session resumption so newer models (e.g. gemini-3.1-flash-
        # live-preview) that close the receive stream after each turn can
        # be transparently reconnected with full context preserved.
        self._config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                role="system", parts=[types.Part(text=system_instruction)]
            ),
            tools=[types.Tool(function_declarations=tools)],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(
                handle=resumption_handle
            ),
        )
        self.last_resumption_handle: str | None = resumption_handle
        self._on_audio_out = on_audio_out
        self._on_tool_call = on_tool_call
        self._on_state_change = on_state_change
        self._session = None
        self._ctx = None
        self._input_buf: list[str] = []
        self._output_buf: list[str] = []
        self._state: str = ""
        self._state_entered_at: float = time.monotonic()
        self.mic_chunks_sent: int = 0
        self.audio_chunks_received: int = 0
        self.recv_messages_total: int = 0
        self._user_turn_end: float | None = None
        self._last_server_msg_at: float = time.monotonic()

    def seconds_since_last_server_message(self) -> float:
        return time.monotonic() - self._last_server_msg_at

    async def __aenter__(self) -> "GeminiLiveSession":
        self._ctx = self._client.aio.live.connect(
            model=self._model, config=self._config
        )
        self._session = await self._ctx.__aenter__()
        logger.info("[gemini] live session opened (model=%s)", self._model)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._ctx is not None:
                await self._ctx.__aexit__(exc_type, exc, tb)
        finally:
            self._session = None
            self._ctx = None
            logger.info("[gemini] live session closed")

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        assert self._session is not None
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm16, mime_type="audio/pcm;rate=16000")
            )
        except Exception as exc:
            ui.audio_send_error(exc)
            logger.exception("send_realtime_input(audio=...) failed")
            raise
        self.mic_chunks_sent += 1

    async def send_audio_stream_end(self) -> None:
        """Flush the automatic VAD buffer. Per Gemini Live docs: "when the
        stream pauses beyond ~1 second, send audioStreamEnd to trigger
        flushing." Without this, the server's VAD stays wedged mid-turn and
        the next user turn is never detected.
        """
        assert self._session is not None
        try:
            await self._session.send_realtime_input(audio_stream_end=True)
            if DEBUG_LIVE:
                ui.info("[dim magenta]→ sent audio_stream_end (flushing VAD)[/]")
        except Exception as exc:
            ui.audio_send_error(exc)
            logger.exception("send_realtime_input(audio_stream_end=True) failed")

    async def send_image(self, jpeg: bytes) -> None:
        assert self._session is not None
        await self._session.send_realtime_input(
            video=types.Blob(data=jpeg, mime_type="image/jpeg")
        )

    async def send_tool_response(
        self, function_responses: list[types.FunctionResponse]
    ) -> None:
        assert self._session is not None
        await self._session.send_tool_response(function_responses=function_responses)

    async def recv_loop(self) -> None:
        """Consume server messages until turn_complete or disconnect.

        IMPORTANT: if the `receive()` async iterator completes normally
        (without an exception), the server has closed the stream. That's a
        silent failure mode — mic_pump keeps feeding a dead socket and the
        user sees "no response" forever. We raise to unwind the TaskGroup.
        """
        assert self._session is not None
        self.recv_messages_total = 0
        ui.info("[dim]→ recv_loop: started[/]")
        try:
            async for message in self._session.receive():
                self.recv_messages_total += 1
                await self._dispatch(message)
        except Exception as exc:
            logger.exception(
                "recv_loop crashed after %d messages", self.recv_messages_total
            )
            ui.error(f"recv_loop died: {exc!r}")
            raise
        # Reaching here means the async iterator exhausted without raising —
        # the server closed the stream. This is almost always unexpected
        # mid-session, so surface it loudly.
        ui.error(
            f"recv_loop exited cleanly after {self.recv_messages_total} "
            "messages — server closed the stream. Mic would have kept "
            "streaming to a dead socket."
        )
        raise RuntimeError("Gemini Live receive() stream closed by server")

    async def _dispatch(self, message) -> None:
        self._last_server_msg_at = time.monotonic()

        if DEBUG_LIVE:
            parts = []
            sc = getattr(message, "server_content", None)
            tc = getattr(message, "tool_call", None)
            tcc = getattr(message, "tool_call_cancellation", None)
            setup = getattr(message, "setup_complete", None)
            go_away = getattr(message, "go_away", None)
            session_res = getattr(message, "session_resumption_update", None)
            usage = getattr(message, "usage_metadata", None)
            if sc is not None:
                inner = []
                if getattr(sc, "model_turn", None) is not None:
                    inner.append("model_turn")
                if getattr(sc, "input_transcription", None) is not None:
                    txt = getattr(sc.input_transcription, "text", "") or ""
                    inner.append(f"input_tx={txt!r}")
                if getattr(sc, "output_transcription", None) is not None:
                    txt = getattr(sc.output_transcription, "text", "") or ""
                    inner.append(f"output_tx={txt!r}")
                if getattr(sc, "generation_complete", False):
                    inner.append("generation_complete")
                if getattr(sc, "turn_complete", False):
                    inner.append("turn_complete")
                if getattr(sc, "interrupted", False):
                    inner.append("interrupted")
                parts.append(f"server_content({', '.join(inner) or '∅'})")
            if tc is not None:
                names = [fc.name for fc in (tc.function_calls or [])]
                parts.append(f"tool_call({names})")
            if tcc is not None:
                parts.append("tool_call_cancellation")
            if setup is not None:
                parts.append("setup_complete")
            if go_away is not None:
                parts.append(f"go_away(time_left={getattr(go_away, 'time_left', '?')})")
            if session_res is not None:
                parts.append("session_resumption_update")
            if usage is not None:
                parts.append("usage_metadata")
            if not parts:
                # Unknown / empty message — dump its fields for inspection
                parts.append(f"UNKNOWN attrs={[a for a in dir(message) if not a.startswith('_')][:12]}")
            ui.server_raw(" | ".join(parts))

        # Capture session-resumption handle — keeps context across reconnects.
        session_res = getattr(message, "session_resumption_update", None)
        if session_res is not None:
            new_handle = getattr(session_res, "new_handle", None)
            if new_handle:
                self.last_resumption_handle = new_handle

        server_content = getattr(message, "server_content", None)
        if server_content is not None:
            # User speech transcription (what Gemini thinks you said)
            input_tx = getattr(server_content, "input_transcription", None)
            if input_tx is not None and getattr(input_tx, "text", None):
                self._set_state("user_speaking")
                self._input_buf.append(input_tx.text)

            # Gemini's own speech transcription (text-of-the-audio it is sending)
            output_tx = getattr(server_content, "output_transcription", None)
            if output_tx is not None and getattr(output_tx, "text", None):
                self._set_state("gemini_speaking")
                self._output_buf.append(output_tx.text)

            # Audio chunks
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is not None:
                for part in getattr(model_turn, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and inline.data:
                        if self.audio_chunks_received == 0 and self._user_turn_end:
                            latency = time.monotonic() - self._user_turn_end
                            ui.turn_timing("first response chunk", latency)
                        self.audio_chunks_received += 1
                        self._set_state("gemini_speaking")
                        await self._on_audio_out(inline.data)

            if getattr(server_content, "interrupted", False):
                ui.server_event("interrupted (Gemini was cut off)")

            if getattr(server_content, "generation_complete", False):
                ui.server_event("generation_complete")

            if getattr(server_content, "turn_complete", False):
                ui.server_event("turn_complete")
                self._flush_transcripts()
                # If Gemini just finished speaking, total turn latency
                if self._user_turn_end is not None and self.audio_chunks_received > 0:
                    total = time.monotonic() - self._user_turn_end
                    ui.turn_timing("full turn", total)
                self._user_turn_end = None
                self.audio_chunks_received = 0
                self._set_state("listening")

        # Tool calls
        tool_call = getattr(message, "tool_call", None)
        if tool_call is not None:
            responses = []
            for fc in getattr(tool_call, "function_calls", []) or []:
                self._set_state("tool:" + fc.name)
                args = dict(fc.args) if fc.args else {}
                result = await self._on_tool_call(fc.name, args)
                responses.append(
                    types.FunctionResponse(
                        id=fc.id, name=fc.name, response=result
                    )
                )
            if responses:
                await self.send_tool_response(responses)

    def _set_state(self, new_state: str) -> None:
        if new_state == self._state:
            return
        # Flush user buffer when leaving user-speaking
        if self._state == "user_speaking" and new_state != "user_speaking":
            self._flush_user_buf()
            if self._user_turn_end is None:
                self._user_turn_end = time.monotonic()
        self._state = new_state
        self._state_entered_at = time.monotonic()
        if self._on_state_change:
            try:
                self._on_state_change(new_state)
            except Exception:
                logger.exception("on_state_change callback failed")
        if new_state == "listening":
            ui.state_listening()
        elif new_state == "user_speaking":
            ui.state_user_speaking()
        elif new_state == "gemini_speaking":
            ui.state_speaking()
        elif new_state.startswith("tool:"):
            ui.state_tool_running(new_state[5:])

    @property
    def current_state(self) -> str:
        return self._state

    def state_elapsed(self) -> float:
        return time.monotonic() - self._state_entered_at

    def _flush_transcripts(self) -> None:
        self._flush_user_buf()
        self._flush_gemini_buf()

    def _flush_user_buf(self) -> None:
        if self._input_buf:
            ui.user_transcript("".join(self._input_buf))
            self._input_buf.clear()

    def _flush_gemini_buf(self) -> None:
        if self._output_buf:
            ui.gemini_transcript("".join(self._output_buf))
            self._output_buf.clear()
