# Conversational Robot

**Autonomous Systems — Tilburg University**

Raspberry Pi 5 (8GB) · Gemma 4 E4B · OpenClaw · llama.cpp · Piper TTS

A fully offline conversational wheeled robot powered by a local LLM. Wake it with "Hey Robot", talk naturally, and it responds via speech. It can see (camera), remember things, move on wheels, and control GPIO peripherals.

## Quick Start (on Raspberry Pi 5)

```bash
# 1. Clone and run setup (downloads model ~4GB, builds llama.cpp, installs deps)
chmod +x scripts/setup.sh
./scripts/setup.sh

# 2. Start the llama.cpp server
./scripts/start_llama_server.sh

# 3. Run the robot
source .venv/bin/activate
python openclaw/main.py
```

### Or install as a systemd service (auto-start on boot):
```bash
sudo cp scripts/robot.service /etc/systemd/system/
sudo systemctl enable --now robot
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Layer 1 — Perception (always on)                │
│  openWakeWord → Audio Capture + Camera Snapshot   │
├──────────────────────────────────────────────────┤
│  Layer 2 — Agent Orchestration (OpenClaw)        │
│  Event Loop → Prompt Builder → Dispatch          │
├──────────────────────────────────────────────────┤
│  Layer 3 — Inference (llama.cpp)                 │
│  Gemma 4 E4B @ localhost:8080 → Tool Calls/Text │
├──────────────────────────────────────────────────┤
│  Layer 4 — Output (Piper TTS + Motors)           │
│  Streaming speech + Wheel control via GPIO       │
└──────────────────────────────────────────────────┘
```

## Repository Structure

```
├── openclaw/                  # Agent framework
│   ├── main.py                # Daemon entry point
│   ├── event_loop.py          # Wake → record → infer → act
│   ├── prompt_builder.py      # Multimodal prompt assembly
│   ├── tool_parser.py         # Streaming JSON tool call parser
│   └── tools/
│       ├── registry.json      # Tool schema for Gemma 4
│       ├── speak.py           # Piper TTS routing
│       ├── vision.py          # Camera + scene description
│       ├── memory_tool.py     # Persistent key-value memory
│       ├── time_tool.py       # System clock
│       ├── reminder.py        # Timed reminders
│       └── gpio.py            # GPIO + wheel motor control
├── perception/
│   ├── wake_word.py           # openWakeWord listener
│   ├── audio_capture.py       # PyAudio + VAD recording
│   └── camera.py              # Pi Camera Module 3
├── tts/
│   └── piper_stream.py        # Streaming Piper TTS wrapper
├── scripts/
│   ├── setup.sh               # Full setup (model download, build, deps)
│   ├── start_llama_server.sh  # Launch llama.cpp HTTP server
│   └── robot.service          # systemd unit file
├── models/                    # Downloaded by setup.sh
├── memory.json                # Persistent robot memory
├── robot_system_prompt.txt    # LLM system prompt
└── requirements.txt           # Python dependencies
```

## Hardware

| Component | Details |
|-----------|---------|
| Compute | Raspberry Pi 5 — 8GB RAM, active cooler |
| LLM | Gemma 4 E4B (Q4_K_M, ~4GB RAM) |
| Inference | llama.cpp (ARM NEON optimised) |
| Microphone | USB microphone |
| Camera | Pi Camera Module 3 |
| Speakers | USB speakers |
| Motors | DC motors via L298N H-bridge (GPIO) |
| Wheels | Differential drive (forward/backward/turn) |

## Motor Wiring (L298N H-Bridge)

Default GPIO pins (BCM) — edit in `openclaw/tools/gpio.py`:

| Pin | Function |
|-----|----------|
| 17 | Left motor forward |
| 27 | Left motor backward |
| 22 | Right motor forward |
| 23 | Right motor backward |
| 12 | Left motor PWM enable |
| 13 | Right motor PWM enable |

## Tools

| Tool | Description |
|------|-------------|
| `speak()` | Route text to Piper TTS |
| `describe_scene()` | Camera snapshot + vision description |
| `remember()` | Persist facts to memory.json |
| `get_time()` | System clock datetime |
| `set_reminder()` | Scheduled future speech |
| `gpio_signal()` | Direct GPIO pin control |
| `move()` | Wheel motor control (forward/backward/turn) |
