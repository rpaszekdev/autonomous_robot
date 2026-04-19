# Conversational Robot — Gemini Live edition

Bidirectional voice + vision robot built on Google's **Gemini Live API**.
Same 7-tool capability set as the original, but inference runs in the cloud,
so it fits an 8 GB MacBook without touching local model weights.

## Architecture (one diagram)

```
  wake (Enter / wake-word)
        │
        ▼
  ┌─── Gemini Live WebSocket ────────────────────────┐
  │                                                  │
  │  mic  ──16 kHz PCM──►  Gemini 3.x  ──24 kHz──► speaker
  │  cam  ──JPEG──────►                 ──tool_call──►  dispatcher ──►  handlers
  │                                   ◄──tool_response──┘
  └──────────────────────────────────────────────────┘
```

All 7 tools preserved: `speak`, `describe_scene`, `remember`, `get_time`,
`set_reminder`, `gpio_signal`, `move`.

## ⚠️ Before first run — confirm the model ID

`GEMINI_MODEL` in `.env` defaults to a placeholder. Set it to the exact
Gemini Live model you want to use (e.g. the latest flash-live ID published
in Google AI Studio). The placeholder **will not work**.

## Mac quickstart (8 GB RAM is plenty — cloud inference)

```bash
cd autonomous_robot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set GOOGLE_API_KEY and GEMINI_MODEL

python -m robot.main --simulate
```

Grant microphone permission when macOS prompts.

**Interactive flow:**
1. Press `ENTER` to wake.
2. Speak into the Mac mic.
3. Robot replies through the Mac speakers.
4. Try: *"What time is it?"*, *"Remember my favourite colour is blue."*,
   *"What do you see?"*, *"Move forward for a second."*
5. `Ctrl-C` to exit — clean shutdown, no zombie audio.

## Raspberry Pi 5 setup

```bash
sudo apt install -y libportaudio2
pip install -r requirements.txt -r requirements-pi.txt

python -m robot.main --wake-model /path/to/hey_jarvis.onnx
```

## Project layout

```
autonomous_robot/
  robot/
    main.py           # CLI entry, wiring
    runtime.py        # wake→session loop (TaskGroup)
    config.py         # env loader
    live/
      session.py      # Gemini Live WebSocket wrapper
      audio_io.py     # mic in + speaker out (sounddevice)
      tools_schema.py # 7 FunctionDeclarations
      dispatcher.py   # tool-call router
    perception/
      camera.py       # MockCamera (Mac) + pi_camera (Pi)
      wake.py         # KeyboardWake + OpenWakeWordWake
    hardware/
      detect.py       # Pi vs Mac autodetect
      motors.py       # MockMotors + gpio_motors
      gpio.py         # MockGpio + rpi_gpio
    tools/            # 7 handlers (one per tool)
  tests/              # pytest unit tests
  requirements.txt
  requirements-pi.txt
  robot_system_prompt.txt
  memory.json
  .env.example
```

## Cost guardrails

- `MAX_SESSION_SECONDS` (default 120) — hard cap per session
- Sessions only start on wake-word / Enter — never continuously

## Tests

```bash
pip install pytest pytest-asyncio
pytest
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing required env var GOOGLE_API_KEY` | Copy `.env.example` to `.env` and fill it in. |
| Audio check fails on Mac | System Settings → Privacy & Security → Microphone → allow Terminal / your Python. |
| `ModuleNotFoundError: google.genai` | `pip install -r requirements.txt` inside an active venv. |
| PortAudio error on Pi | `sudo apt install libportaudio2`. |
| Model ID rejected | Update `GEMINI_MODEL` in `.env` to a currently-released Live model. |
