"""Prompt Builder — Assembles multimodal prompt per invocation.

Injects: system prompt, tool schema, persistent memory,
last 6 turns of history, audio, camera frame.
Context budget capped at 4096 tokens.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

TOOLS_REGISTRY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tools", "registry.json"
)


class PromptBuilder:
    def __init__(self, system_prompt_path: str, memory_path: str):
        self.system_prompt_path = system_prompt_path
        self.memory_path = memory_path

        # Load system prompt
        with open(system_prompt_path, "r") as f:
            self._system_prompt = f.read().strip()

        # Load tool schema
        with open(TOOLS_REGISTRY, "r") as f:
            self._tools = json.load(f)

    def _load_memory(self) -> str:
        """Load persistent memory key-value pairs."""
        if not os.path.exists(self.memory_path):
            return ""
        try:
            with open(self.memory_path, "r") as f:
                mem = json.load(f)
            if not mem:
                return ""
            lines = [f"- {k}: {v}" for k, v in mem.items()]
            return "Persistent memory:\n" + "\n".join(lines)
        except (json.JSONDecodeError, IOError):
            return ""

    def build(self, audio_b64: str, image_b64: str | None,
              history: list[dict]) -> list[dict]:
        """Build the full message list for llama.cpp chat completion."""
        memory_block = self._load_memory()

        system_content = self._system_prompt
        if memory_block:
            system_content += f"\n\n{memory_block}"

        messages = [
            {"role": "system", "content": system_content},
        ]

        # Add conversation history (last 6 turns)
        for msg in history[-12:]:
            messages.append(msg)

        # Build multimodal user turn
        user_content = []

        # Audio input (raw PCM as base64)
        user_content.append({
            "type": "audio",
            "audio": f"data:audio/pcm;base64,{audio_b64}",
        })

        # Image input if available
        if image_b64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            })

        messages.append({"role": "user", "content": user_content})

        return messages

    @property
    def tools_schema(self) -> list[dict]:
        """Return tool definitions for function calling."""
        return self._tools
