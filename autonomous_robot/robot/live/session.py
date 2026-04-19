"""Gemini Live WebSocket session wrapper.

Thin, async context-manager around google-genai's live API. Owns:
  - sending realtime audio frames + image blobs
  - receiving audio chunks and dispatching them to a playback callback
  - receiving tool_calls and posting tool_responses
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from google import genai
from google.genai import types

from robot import ui

logger = logging.getLogger(__name__)

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
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                role="system", parts=[types.Part(text=system_instruction)]
            ),
            tools=[types.Tool(function_declarations=tools)],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self._on_audio_out = on_audio_out
        self._on_tool_call = on_tool_call
        self._session = None
        self._ctx = None
        self._input_buf: list[str] = []
        self._output_buf: list[str] = []
        self._state: str = ""  # tracks last announced state

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
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm16, mime_type="audio/pcm;rate=16000")
        )

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
        """Consume server messages until turn_complete or disconnect."""
        assert self._session is not None
        async for message in self._session.receive():
            await self._dispatch(message)

    async def _dispatch(self, message) -> None:
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
                        self._set_state("gemini_speaking")
                        await self._on_audio_out(inline.data)

            if getattr(server_content, "turn_complete", False):
                self._flush_transcripts()
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
        # Flush buffers at major transitions
        if new_state == "gemini_speaking" and self._input_buf:
            self._flush_user_buf()
        self._state = new_state
        if new_state == "listening":
            ui.state_listening()
        elif new_state == "user_speaking":
            ui.state_user_speaking()
        elif new_state == "gemini_speaking":
            ui.state_speaking()
        elif new_state.startswith("tool:"):
            ui.state_tool_running(new_state[5:])

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
