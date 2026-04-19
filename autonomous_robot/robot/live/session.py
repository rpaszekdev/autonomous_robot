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
        )
        self._on_audio_out = on_audio_out
        self._on_tool_call = on_tool_call
        self._session = None
        self._ctx = None

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
        # Audio chunks arrive as inline_data on server_content parts
        server_content = getattr(message, "server_content", None)
        if server_content is not None:
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is not None:
                for part in getattr(model_turn, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and inline.data:
                        await self._on_audio_out(inline.data)

        # Tool calls
        tool_call = getattr(message, "tool_call", None)
        if tool_call is not None:
            responses = []
            for fc in getattr(tool_call, "function_calls", []) or []:
                args = dict(fc.args) if fc.args else {}
                result = await self._on_tool_call(fc.name, args)
                responses.append(
                    types.FunctionResponse(
                        id=fc.id, name=fc.name, response=result
                    )
                )
            if responses:
                await self.send_tool_response(responses)
