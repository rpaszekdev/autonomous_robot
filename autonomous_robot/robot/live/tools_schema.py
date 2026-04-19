"""Gemini FunctionDeclarations for the 7 robot tools.

Names and argument shapes preserved verbatim from the original
openclaw tool registry so the system prompt remains portable.
"""

from __future__ import annotations

from google.genai import types

SPEAK = types.FunctionDeclaration(
    name="speak",
    description=(
        "Speak text aloud. Note: Gemini native audio output already handles "
        "speech, so this is only needed when you want to emit a specific "
        "phrase without a full response turn. Prefer speaking naturally."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "text": types.Schema(type=types.Type.STRING, description="Text to speak."),
        },
        required=["text"],
    ),
)

DESCRIBE_SCENE = types.FunctionDeclaration(
    name="describe_scene",
    description=(
        "Take a fresh camera snapshot and receive it as visual context. "
        "Use when asked about surroundings or visual questions."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "focus": types.Schema(
                type=types.Type.STRING,
                description="Optional focus area or object to pay attention to.",
            ),
        },
    ),
)

REMEMBER = types.FunctionDeclaration(
    name="remember",
    description="Store a fact in persistent memory, recalled in future conversations.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "key": types.Schema(
                type=types.Type.STRING,
                description="Short label (e.g. 'user_name', 'favorite_color').",
            ),
            "value": types.Schema(type=types.Type.STRING, description="Value to remember."),
        },
        required=["key", "value"],
    ),
)

GET_TIME = types.FunctionDeclaration(
    name="get_time",
    description="Return the current local date and time.",
    parameters=types.Schema(type=types.Type.OBJECT, properties={}),
)

SET_REMINDER = types.FunctionDeclaration(
    name="set_reminder",
    description="Speak a reminder message after a delay in seconds.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "message": types.Schema(type=types.Type.STRING, description="Reminder text."),
            "delay_seconds": types.Schema(
                type=types.Type.INTEGER, description="Seconds from now to fire."
            ),
        },
        required=["message", "delay_seconds"],
    ),
)

GPIO_SIGNAL = types.FunctionDeclaration(
    name="gpio_signal",
    description="Control a GPIO pin (LED, relay, servo).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "pin": types.Schema(type=types.Type.INTEGER, description="BCM pin number."),
            "state": types.Schema(
                type=types.Type.BOOLEAN, description="True = HIGH, False = LOW."
            ),
            "duration_ms": types.Schema(
                type=types.Type.INTEGER,
                description="Optional auto-reset after this many ms.",
            ),
        },
        required=["pin", "state"],
    ),
)

MOVE = types.FunctionDeclaration(
    name="move",
    description="Drive the wheeled robot.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "direction": types.Schema(
                type=types.Type.STRING,
                enum=["forward", "backward", "left", "right", "stop"],
            ),
            "speed": types.Schema(
                type=types.Type.NUMBER, description="0.0 to 1.0 (default 0.5)."
            ),
            "duration_ms": types.Schema(
                type=types.Type.INTEGER, description="Duration in ms (default 1000)."
            ),
        },
        required=["direction"],
    ),
)

ALL: list[types.FunctionDeclaration] = [
    SPEAK,
    DESCRIBE_SCENE,
    REMEMBER,
    GET_TIME,
    SET_REMINDER,
    GPIO_SIGNAL,
    MOVE,
]
