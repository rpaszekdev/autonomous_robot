"""Gemini FunctionDeclarations for all robot tools."""

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

ENROLL_FACE = types.FunctionDeclaration(
    name="enroll_face",
    description=(
        "Learn the current user's face so the robot can recognise them in "
        "future sessions. Call this when the user says something like "
        "'remember my face', 'learn who I am', or gives their name and "
        "wants to be remembered."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "name": types.Schema(
                type=types.Type.STRING,
                description="The person's name or preferred name (e.g. 'David').",
            ),
        },
        required=["name"],
    ),
)

SET_LEDS = types.FunctionDeclaration(
    name="set_leds",
    description=(
        "Control the robot's LEDs to express emotions, play games, send signals, "
        "or create any visual effect. You have 4 LEDs: green, blue, yellow, red. "
        "Use them creatively — show mood (green=happy, red=angry, blue=thinking), "
        "play games (Simon Says, binary counting), flash alerts, blink morse code, "
        "or anything a person suggests. You can set LEDs instantly or provide an "
        "animated pattern of frames. Use this PROACTIVELY during conversation to "
        "express yourself, not just when asked."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "leds": types.Schema(
                type=types.Type.OBJECT,
                description=(
                    "Set each LED on/off instantly. Keys: green, blue, yellow, red. "
                    "Values: true (on) or false (off). Only include LEDs you want to change."
                ),
                properties={
                    "green": types.Schema(type=types.Type.BOOLEAN),
                    "blue": types.Schema(type=types.Type.BOOLEAN),
                    "yellow": types.Schema(type=types.Type.BOOLEAN),
                    "red": types.Schema(type=types.Type.BOOLEAN),
                },
            ),
            "pattern": types.Schema(
                type=types.Type.ARRAY,
                description=(
                    "Animated sequence of LED frames. Each frame has 'leds' (which LEDs on/off) "
                    "and 'duration_ms' (how long to hold, default 300ms). Use for blinking, "
                    "morse code, chase patterns, counting, etc. Max 50 frames."
                ),
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "leds": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "green": types.Schema(type=types.Type.BOOLEAN),
                                "blue": types.Schema(type=types.Type.BOOLEAN),
                                "yellow": types.Schema(type=types.Type.BOOLEAN),
                                "red": types.Schema(type=types.Type.BOOLEAN),
                            },
                        ),
                        "duration_ms": types.Schema(
                            type=types.Type.INTEGER,
                            description="How long to hold this frame in ms (default 300).",
                        ),
                    },
                ),
            ),
        },
    ),
)

SET_DISPLAY = types.FunctionDeclaration(
    name="set_display",
    description=(
        "Control the 8x8 LED dot matrix display — your face and creative canvas! "
        "IMPORTANT: Use 'face' to set emotion faces (happy, sad, neutral, angry, surprised, "
        "excited, sleepy, wink) — these automatically animate a talking mouth when you speak! "
        "Set the face BEFORE you reply so the mouth moves while you talk. "
        "Use 'play_animation' for built-in animations like 'wave' when someone says hi! "
        "Use 'pixels' for custom 8x8 pixel art — draw ANYTHING you can imagine. "
        "Use 'animation' to create your OWN multi-frame animations from scratch — "
        "be an artist! Draw fireworks, rain, bouncing balls, spirals, whatever fits the moment. "
        "Use PROACTIVELY — always set a face before responding to show your mood."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "face": types.Schema(
                type=types.Type.STRING,
                description=(
                    "Set an emotion face that animates when you speak. "
                    "Options: happy, sad, neutral, angry, surprised, excited, sleepy, wink. "
                    "ALWAYS set this before replying so the mouth moves while you talk."
                ),
            ),
            "icon": types.Schema(
                type=types.Type.STRING,
                description=(
                    "Show a non-face icon: heart, check, x, question, "
                    "arrow_up, skull. These don't animate when speaking."
                ),
            ),
            "pixels": types.Schema(
                type=types.Type.ARRAY,
                description=(
                    "Custom 8x8 pixel grid. Provide 8 rows, each row is 8 values "
                    "(1=on, 0=off). Draw anything — letters, shapes, pixel art."
                ),
                items=types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.INTEGER),
                ),
            ),
            "tictactoe": types.Schema(
                type=types.Type.STRING,
                description=(
                    "Render a tic-tac-toe board on the display. Pass 9 characters: "
                    "X, O, or _ (empty). Positions are left-to-right, top-to-bottom. "
                    "Example: 'X_O_X____' means X in top-left and center, O in top-right. "
                    "The board is drawn with grid lines and X/O markers. "
                    "Returns game status: in_progress, X_wins, O_wins, or draw. "
                    "You are O, the human is X. Update the board after each move."
                ),
            ),
            "text": types.Schema(
                type=types.Type.STRING,
                description="Show text. Only 1-2 characters fit without scrolling.",
            ),
            "scroll": types.Schema(
                type=types.Type.BOOLEAN,
                description="If true, scroll the text across the display.",
            ),
            "play_animation": types.Schema(
                type=types.Type.STRING,
                description=(
                    "Play a built-in animation by name: 'wave' (wave hello!), "
                    "'heartbeat' (pulsing heart), 'sparkle' (twinkling stars). "
                    "Use 'wave' when someone says hi or greets you!"
                ),
            ),
            "animation": types.Schema(
                type=types.Type.ARRAY,
                description=(
                    "Create your OWN custom animation! Sequence of frames, each with "
                    "'pixels' (8x8 grid) and 'duration_ms'. Max 30 frames. "
                    "Be creative — draw anything: fireworks, rain, bouncing ball, "
                    "explosions, spinning shapes, dancing figures. Invent new things! "
                    "You're an artist with a tiny 8x8 canvas."
                ),
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "icon": types.Schema(type=types.Type.STRING),
                        "pixels": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.INTEGER),
                            ),
                        ),
                        "duration_ms": types.Schema(
                            type=types.Type.INTEGER,
                            description="How long to hold this frame (default 300ms).",
                        ),
                    },
                ),
            ),
            "brightness": types.Schema(
                type=types.Type.INTEGER,
                description="Set display brightness 0-255.",
            ),
            "clear": types.Schema(
                type=types.Type.BOOLEAN,
                description="Turn off all pixels.",
            ),
        },
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
    ENROLL_FACE,
    SET_LEDS,
    SET_DISPLAY,
]
