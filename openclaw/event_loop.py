"""OpenClaw Event Loop — Polling + dispatch.

On wake word: record audio + capture image → build prompt →
send to llama.cpp → parse response → execute tools or speak.
"""

import os
import json
import logging
import subprocess
import threading
import base64
import requests

logger = logging.getLogger(__name__)

MAX_TOOL_HOPS = 3


class EventLoop:
    def __init__(self, llama_url, audio_capture, camera, tts,
                 prompt_builder, tool_parser, ack_tone_path=None):
        self.llama_url = llama_url
        self.audio = audio_capture
        self.camera = camera
        self.tts = tts
        self.prompt_builder = prompt_builder
        self.tool_parser = tool_parser
        self.ack_tone_path = ack_tone_path
        self._lock = threading.Lock()
        self.history: list[dict] = []

    def _play_ack_tone(self):
        """Play short acknowledgment tone to confirm wake word heard."""
        if self.ack_tone_path and os.path.exists(self.ack_tone_path):
            try:
                subprocess.Popen(
                    ["aplay", "-q", self.ack_tone_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass

    def on_wake_word(self):
        """Called by wake word detector. Runs agent turn in a thread."""
        threading.Thread(target=self._handle_turn, daemon=True).start()

    def _handle_turn(self):
        if not self._lock.acquire(blocking=False):
            logger.debug("Turn already in progress, ignoring wake word")
            return

        try:
            # Step 1: Acknowledge
            self._play_ack_tone()

            # Step 2: Capture audio + image in parallel
            image_b64 = [None]
            def capture_image():
                try:
                    image_b64[0] = self.camera.capture_base64()
                except Exception as e:
                    logger.warning("Camera capture failed: %s", e)

            img_thread = threading.Thread(target=capture_image)
            img_thread.start()

            audio_pcm = self.audio.record_until_silence()
            img_thread.join(timeout=2.0)

            # Encode audio as base64 for Gemma 4 multimodal input
            audio_b64 = base64.b64encode(audio_pcm).decode("ascii")

            # Step 3: Build prompt and dispatch to LLM
            self._agent_loop(audio_b64, image_b64[0])

        except Exception:
            logger.exception("Error during turn")
        finally:
            self._lock.release()

    def _agent_loop(self, audio_b64: str, image_b64: str | None):
        """Run the agent loop with tool call support (max 3 hops)."""
        messages = self.prompt_builder.build(
            audio_b64=audio_b64,
            image_b64=image_b64,
            history=self.history,
        )

        for hop in range(MAX_TOOL_HOPS):
            response_text = self._call_llama(messages)
            if not response_text:
                break

            # Check for tool calls
            tool_calls = self.tool_parser.parse(response_text)
            if not tool_calls:
                # Plain text response → speak it
                self.tts.speak(response_text)
                self._update_history("assistant", response_text)
                break

            # Execute tool calls and inject results
            for tool_call in tool_calls:
                result = self.tool_parser.execute(tool_call)
                messages.append({
                    "role": "assistant",
                    "content": response_text,
                })
                messages.append({
                    "role": "user",
                    "content": f"[Tool result for {tool_call['name']}]: {json.dumps(result)}",
                })
                logger.info("Tool %s → %s", tool_call["name"], result)
        else:
            logger.warning("Max tool hops (%d) reached", MAX_TOOL_HOPS)

    def _call_llama(self, messages: list[dict]) -> str | None:
        """Send messages to llama.cpp /v1/chat/completions and stream response."""
        try:
            resp = requests.post(
                f"{self.llama_url}/v1/chat/completions",
                json={
                    "messages": messages,
                    "max_tokens": 256,
                    "stream": True,
                    "temperature": 0.7,
                },
                stream=True,
                timeout=30,
            )
            resp.raise_for_status()

            full_text = []
            sentence_buffer = []

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        full_text.append(token)
                        sentence_buffer.append(token)
                        # Stream sentence-by-sentence to TTS
                        joined = "".join(sentence_buffer)
                        if any(joined.rstrip().endswith(p) for p in ".!?"):
                            self.tts.speak_async(joined.strip())
                            sentence_buffer.clear()
                except (json.JSONDecodeError, KeyError):
                    continue

            # Flush remaining text
            remaining = "".join(sentence_buffer).strip()
            if remaining:
                self.tts.speak_async(remaining)

            return "".join(full_text)

        except requests.RequestException as e:
            logger.error("llama.cpp request failed: %s", e)
            return None

    def _update_history(self, role: str, content: str):
        """Keep last 6 turns of history."""
        self.history.append({"role": role, "content": content})
        if len(self.history) > 12:  # 6 turns = 12 messages (user+assistant)
            self.history = self.history[-12:]
