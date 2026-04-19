"""Tool Parser — Streaming JSON tool call parser.

Parses Gemma 4 native tool call output and dispatches execution.
"""

import json
import re
import logging

logger = logging.getLogger(__name__)

# Import tool implementations
from openclaw.tools.speak import tool_speak
from openclaw.tools.vision import tool_describe_scene
from openclaw.tools.memory_tool import tool_remember
from openclaw.tools.gpio import tool_gpio_signal, tool_move
from openclaw.tools.time_tool import tool_get_time
from openclaw.tools.reminder import tool_set_reminder

# Tool dispatch table
TOOL_REGISTRY = {
    "speak": tool_speak,
    "describe_scene": tool_describe_scene,
    "remember": tool_remember,
    "get_time": tool_get_time,
    "set_reminder": tool_set_reminder,
    "gpio_signal": tool_gpio_signal,
    "move": tool_move,
}


class ToolParser:
    # Gemma 4 outputs tool calls in this format:
    # ```tool_call\n{"name": "...", "arguments": {...}}\n```
    TOOL_CALL_PATTERN = re.compile(
        r'```tool_call\s*\n(\{.*?\})\s*\n```',
        re.DOTALL,
    )

    def parse(self, text: str) -> list[dict]:
        """Extract tool calls from LLM output.

        Returns:
            List of dicts with 'name' and 'arguments' keys.
        """
        calls = []
        for match in self.TOOL_CALL_PATTERN.finditer(text):
            try:
                call = json.loads(match.group(1))
                if "name" in call:
                    calls.append(call)
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool call: %s", match.group(1))
        return calls

    def execute(self, tool_call: dict) -> dict:
        """Execute a parsed tool call.

        Returns:
            Result dict from the tool.
        """
        name = tool_call.get("name", "")
        args = tool_call.get("arguments", {})

        handler = TOOL_REGISTRY.get(name)
        if handler is None:
            logger.error("Unknown tool: %s", name)
            return {"error": f"Unknown tool: {name}"}

        try:
            return handler(**args)
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return {"error": str(e)}
