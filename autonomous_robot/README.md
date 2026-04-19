# Conversational Robot — Gemini Live edition

A voice + vision robot built on Google's **Gemini Live API** (bidirectional
WebSocket with native audio in, audio out, video frames in, and function
calling). Cloud inference means **no local model weights**, so it runs
comfortably on an 8 GB MacBook. The same codebase targets a Raspberry Pi 5
for the physical robot.

Branch: **`gemini-live-integration`** (greenfield; preserves the original
Ollama/Gemma4 implementation on the `laptop-testing` branch).

```
┌───────────────────── GEMINI LIVE SESSION ────────────────────┐
│                                                              │
│  mic ──16 kHz PCM──►  Gemini 3.x ──24 kHz PCM──► speaker     │
│  cam ──JPEG─────►                ──tool_call──► dispatcher   │
│                                  ◄─tool_response─┘           │
└──────────────────────────────────────────────────────────────┘
```

---

## Features

- **Voice in / voice out** — server-side VAD on Gemini; native 24 kHz audio
  response played through your speakers
- **Webcam vision** — real Mac/Linux webcam via OpenCV, or Pi Camera Module 3
- **Seven tools** — speak, describe_scene, remember, get_time, set_reminder,
  gpio_signal, move (simulated on Mac, real GPIO on Pi)
- **Persistent memory** — flat JSON K-V store, injected into the system prompt
- **Keyboard wake** on Mac, **openWakeWord** on Pi
- **Rich CLI UI** — colored state banners, transcripts, audio-chunk dots,
  tool-call events — you always know what Gemini is doing
- **Cost guardrails** — hard per-session timeout, per-hour session cap
- **Cross-platform** — auto-detects Pi vs Mac; optional `--simulate` flag

---

## Prerequisites

| | Mac | Raspberry Pi 5 |
|---|---|---|
| Python | 3.11+ | 3.11+ |
| RAM    | 4 GB+ | 8 GB recommended |
| Mic    | built-in or USB | USB mic |
| Cam    | built-in or USB | Pi Camera Module 3 |
| Network| required — cloud API | required |
| System | — | `sudo apt install libportaudio2` |

You also need:
- A **Google AI Studio API key** with Gemini Live access
  → https://aistudio.google.com/apikey
- The **exact Live model ID** your key can use (list your own in step 4 below)

---

## ⚠️ Read first: confirm the model ID

The `.env.example` default (`gemini-3.1-flash-live-preview`) was current as of
**2026-04**. Live model IDs rotate — if it stops working, run step 4 to see
what your key currently accepts.

---

## Quickstart — macOS

### 1. Clone and check out the branch

```bash
git clone https://github.com/rpaszekdev/autonomous_robot.git
cd autonomous_robot
git checkout gemini-live-integration
cd autonomous_robot
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Set up your `.env`

```bash
cp .env.example .env
```

Open `.env` in any editor and fill in:
```
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.1-flash-live-preview   # change if your key needs a different one
```

### 4. (Optional but recommended) Verify model + list webcams

```bash
# Confirm env + audio devices + SDK are happy
python scripts/preflight.py

# Confirm the model ID actually works with your key
python scripts/check_model.py

# See which webcams are available
python -m robot.main --list-cameras
```

If `check_model.py` fails with `1008 ... is not found`, list the Live-capable
models your key sees:

```python
python -c "
from google import genai; from dotenv import load_dotenv; import os
load_dotenv('.env')
c = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
for m in c.models.list():
    methods = getattr(m, 'supported_actions', []) or []
    if 'bidiGenerateContent' in methods:
        print(m.name)
"
```

Copy one of the printed names (strip the `models/` prefix) into `GEMINI_MODEL`.

### 5. Grant Mic + Camera permission (first run)

Open **System Settings → Privacy & Security**, then enable your terminal app
(Terminal / iTerm / VS Code) under both **Microphone** and **Camera**. Quit and
reopen the terminal for changes to take effect.

### 6. Run it

```bash
# Mock camera (blue test image — use only to verify plumbing)
python -m robot.main --simulate

# Real built-in webcam
python -m robot.main --simulate --webcam

# Specific local webcam index (if you have multiple)
python -m robot.main --simulate --webcam --webcam-index 1

# IP camera — RTSP (typical for most network cams)
python -m robot.main --simulate --camera-url "rtsp://user:pass@192.168.1.50:554/stream1"

# IP camera — HTTP MJPEG (common on phone-as-webcam apps like IP Webcam)
python -m robot.main --simulate --camera-url "http://192.168.1.50:8080/video"
```

⚠ **Without `--webcam` or `--camera-url` you get the mock camera**, which
returns a blue test image — Gemini will say "I see a solid blue screen".
Always add one of those flags to give Gemini real vision.

**Usage:**
1. Press **Enter** when you see `🎙 LISTENING`
2. Speak naturally
3. Ctrl-C to quit

---

## Quickstart — Raspberry Pi 5

```bash
sudo apt install libportaudio2
git clone https://github.com/rpaszekdev/autonomous_robot.git
cd autonomous_robot
git checkout gemini-live-integration
cd autonomous_robot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-pi.txt

cp .env.example .env
# edit .env (GOOGLE_API_KEY, GEMINI_MODEL)

# download an openWakeWord .onnx file to, e.g., models/hey_jarvis.onnx
python -m robot.main --wake-model models/hey_jarvis.onnx
```

---

## What you'll see (CLI UI reference)

```
╭──────── 🤖 GEMINI LIVE ROBOT ────────╮
│ Model   gemini-3.1-flash-live-preview│
│ Mode    simulate                     │
│ Camera  real webcam — index 0 · 1280x720
╰──────────────────────────────────────╯
>>> Press ENTER to wake the robot

─────────── ▶ Session 1 started ───────────
  📷 CAMERA    sent 48,212 bytes (session open)
  🎤 MIC       capturing at 16 kHz
  🔊 SPEAKER   ready at 24 kHz
  🎙  LISTENING  — speak now
  🗨  YOU SPEAKING
  you:     "what do you see"
  ⚙  RUNNING TOOL  — describe_scene
  📷 CAMERA    sent 52,104 bytes (describe_scene)
   ↳ ok=True, bytes=52104, focus=None
  🗣  GEMINI SPEAKING
·················
  gemini:  "I see you at a desk with a laptop and a coffee mug."
  🎙  LISTENING  — speak now
```

Legend:
- **🎙 LISTENING** — ready for you to speak
- **🗨 YOU SPEAKING** — streaming your mic audio to Gemini
- **💭 THINKING** — Gemini processing
- **🗣 GEMINI SPEAKING** — audio streaming back (each `·` is one chunk)
- **⚙ RUNNING TOOL** — Gemini called a function; executing now
- **📷 CAMERA** — a frame was sent to Gemini
- **`you: "..."`** — exact transcription of your speech (from Gemini)
- **`gemini: "..."`** — exact transcription of Gemini's response

---

## Things to try

| Say | Tool called | Expected outcome |
|---|---|---|
| *"What time is it?"* | `get_time` | Speaks current date/time |
| *"Remember my favourite colour is teal."* | `remember` | `memory.json` updated; future sessions recall it |
| *"What's my favourite colour?"* | (none — from memory preamble) | Recalls "teal" |
| *"What do you see?"* | `describe_scene` | Sends fresh frame; describes it |
| *"What colour is my shirt?"* | `describe_scene` | Fresh frame + answer |
| *"Remind me in 5 seconds to stretch."* | `set_reminder` | Speaks the reminder after 5 s |
| *"Move forward for one second."* | `move` | Log line `[SIM motors] FORWARD speed=0.50` |
| *"Turn GPIO pin 17 on for half a second."* | `gpio_signal` | Log line `[SIM gpio] pin=17 HIGH` |

---

## Environment variables (`.env`)

| Var | Required | Default | Notes |
|---|---|---|---|
| `GOOGLE_API_KEY` | yes | — | AI Studio key with Gemini Live access |
| `GEMINI_MODEL`   | no  | `gemini-3.1-flash-live-preview` | Must support `bidiGenerateContent` |
| `SIMULATE`       | no  | `0` | Force mock hardware (auto-on off-Pi) |
| `MAX_SESSION_SECONDS` | no | `120` | Hard cap per session (cost guard) |
| `MAX_SESSIONS_PER_HOUR` | no | `30` | (reserved for future rate-limit) |
| `SESSION_IDLE_SECONDS` | no | `15` | (reserved) |
| `SD_INPUT_DEVICE`  | no | — | Override default mic |
| `SD_OUTPUT_DEVICE` | no | — | Override default speaker |

---

## CLI flags

```
python -m robot.main [--simulate] [--webcam] [--webcam-index N]
                     [--list-cameras] [--wake-model PATH]
```

- `--simulate` — force mock hardware (auto-on when not on a Pi)
- `--webcam` — use the real local webcam via OpenCV (Mac/Linux)
- `--webcam-index N` — pick a specific local webcam (default 0)
- `--camera-url URL` — connect to an IP camera (RTSP / HTTP MJPEG / any OpenCV-readable URL)
- `--list-cameras` — scan local indices 0–3 and exit
- `--wake-model PATH` — openWakeWord `.onnx` path (Pi only)

---

## Architecture

```
autonomous_robot/
  robot/
    main.py           # CLI entry, service wiring
    runtime.py        # wake → session loop, asyncio TaskGroup
    config.py         # env loader
    ui.py             # Rich-based CLI UI
    live/
      session.py      # Gemini Live WebSocket wrapper (google-genai)
      audio_io.py     # sounddevice mic in + speaker out
      tools_schema.py # 7 FunctionDeclarations
      dispatcher.py   # tool-call router
    perception/
      camera.py       # MockCamera + OpenCVCamera + pi_camera
      wake.py         # KeyboardWake + OpenWakeWordWake
    hardware/
      detect.py       # Pi-vs-other autodetect
      motors.py       # MockMotors + gpio_motors (differential drive)
      gpio.py         # MockGpio + rpi_gpio
    tools/            # 7 handlers, one per tool
  tests/              # 13 pytest unit tests
  scripts/
    preflight.py      # env + audio + SDK check (no network)
    check_model.py    # opens a Live session briefly to validate model ID
  requirements.txt
  requirements-pi.txt
  robot_system_prompt.txt
  memory.json         # gitignored — local state
  .env                # gitignored — your secrets
  .env.example
```

Why this shape: many small files (< 400 LOC each), one responsibility per
module, DI for easy mocking in tests, `Protocol` types so Pi vs Mac
implementations are interchangeable.

---

## Running the tests

```bash
source .venv/bin/activate
pip install pytest pytest-asyncio
pytest
```

13 tests: dispatcher, tool schemas, memory I/O, tool handlers (time, motion,
gpio, reminder).

---

## Cost guardrails

- `MAX_SESSION_SECONDS` (default **120 s**) — watchdog closes the session
- Sessions only open on wake (Enter on Mac, wake-word on Pi). The robot does
  not hold a session open idle.
- Watch the `📷 CAMERA sent N bytes` and `···` audio-chunk dots to know
  when you're paying for streaming.

Monitor your usage: https://aistudio.google.com/

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing required env var GOOGLE_API_KEY` | Copy `.env.example` to `.env`, fill in, save. |
| `1008 ... is not found for API version v1beta` | Your `GEMINI_MODEL` ID is wrong / not accessible. List models (see Quickstart §4) and pick one. |
| `realtime_input.media_chunks is deprecated` | You're on an older commit. `git pull`. |
| Camera permission denied | System Settings → Privacy & Security → Camera → enable your terminal. **Restart** the terminal. |
| Microphone permission denied | Same path under **Microphone**. |
| `Could not open webcam index 0` | Camera not granted / in use by another app. Close Zoom/FaceTime; try `--list-cameras`. |
| Initial frame is very small (< 8 KB) | Camera is still dark; say *"what do you see"* to get a fresh frame after auto-exposure settles. |
| `mic backpressure: dropped N frames` | Network slow; harmless bursts. Sustained warnings = check connection. |
| PortAudio error on Pi | `sudo apt install libportaudio2`. |
| Robot doesn't answer visual questions | System prompt should now force `describe_scene`. If not, restart to pick up latest prompt. |

---

## Development & contributing

```bash
# While iterating, keep tests green:
pytest

# Before commits on UI / code:
python scripts/preflight.py   # env + audio
python scripts/check_model.py # model + API
```

Coding style (follows project CLAUDE.md rules):
- small focused files (< 400 LOC)
- immutable where possible
- no hidden error swallowing
- no comments explaining *what* — only non-obvious *why*

---

## License / Credit

Built for the Tilburg University Autonomous Systems course. Preserves the
behaviour and tool surface of the original offline Ollama/Gemma4
implementation (see `laptop-testing` branch).
