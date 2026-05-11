# Autonomous Robot — Project Guide

## Overview
Raspberry Pi 5 conversational robot powered by Gemini Live. Wake word → record audio + capture image → Gemini inference → tool calls / speech output.

## Architecture
- **robot/main.py** — CLI entry point (`python3 -m robot.main`)
- **robot/runtime.py** — Session lifecycle: wake → Gemini Live session → tool dispatch → close
- **robot/live/audio_io.py** — Mic/speaker I/O via sounddevice (BOYA mini @ 48kHz → resample to 16kHz for Gemini)
- **robot/live/network_mic.py** — TCP mic stream replacement for when USB mic is on a remote Mac
- **robot/live/session.py** — Gemini Live WebSocket session
- **robot/live/dispatcher.py** — Tool call routing
- **robot/perception/** — Camera, wake word, face ID
- **robot/tools/** — speak, vision, memory, motion, GPIO, reminders
- **openclaw/** — Legacy agent framework (PyAudio + llama.cpp). Not used in current Gemini Live setup.

## Key Audio Config
- Gemini expects **16kHz mono 16-bit PCM** input
- Gemini sends **24kHz mono 16-bit PCM** output
- Hardware mic (BOYA mini) runs at 48kHz, resampled in `audio_io.py`
- Speaker output resampled from 24kHz → 48kHz for HDMI

## Network Audio (Mac mic → Pi)
When the USB mic can't be plugged into the Pi directly:

**Pi side:**
```bash
cd ~/autonomous_robot/autonomous_robot/autonomous_robot
source .venv/bin/activate
python3 -m robot.main --network-audio
```
This starts a TCP server on port 9999 waiting for mic audio.

**Mac side (two terminals):**

**For personal hotspot or local network (mDNS works):**
```bash
# Terminal 1 — send mic audio to Pi
python scripts/mac_mic_sender.py raspberrypi.local

# Terminal 2 — hear robot audio from Pi
python scripts/play_robot_audio.py
```

**For enterprise networks (eduroam, corporate WiFi — mDNS blocked):**
```bash
# Terminal 1 — send mic audio to Pi (use IP instead of hostname)
python scripts/mac_mic_sender.py 172.20.10.5

# Terminal 2 — hear robot audio from Pi
python scripts/play_robot_audio.py 172.20.10.5
```

Or use environment variables:
```bash
export PI_HOST=172.20.10.5  # or raspberrypi.local
python scripts/mac_mic_sender.py $PI_HOST
python scripts/play_robot_audio.py
```

- `mac_mic_sender.py` captures Mac mic, resamples to 16kHz, streams over TCP port 9999
- `play_robot_audio.py` connects to Pi TCP port 9001, plays 24kHz robot speech on Mac speakers
- Both auto-reconnect on disconnect
- **Use IP address (172.20.10.5) on networks that block mDNS (eduroam, corporate WiFi)**

## Pi Connection
- Host: `raspberrypi.local` / `172.20.10.5`
- User: `davidtzuke`
- SSH key: `~/.ssh/pi_key`
- Robot code path: `~/autonomous_robot/autonomous_robot/autonomous_robot/`

## Running on Pi
```bash
cd ~/autonomous_robot/autonomous_robot/autonomous_robot
source .venv/bin/activate
python3 -m robot.main                    # normal (local mic)
python3 -m robot.main --network-audio    # Mac mic over TCP
python3 -m robot.main --simulate         # mock hardware
python3 -m robot.main --webcam           # use webcam instead of Pi camera
```

## Dependencies
- Python 3.13 on Pi
- `tflite-runtime` doesn't support 3.13 — use `onnxruntime` for openwakeword
- Mac scripts need: `pip install sounddevice numpy scipy`

## Conventions
- No Co-Authored-By lines in commits
- Config is a frozen dataclass — don't assign new fields to it, pass params explicitly
- `SpeakerStream` has a built-in TCP server on port 9001 for remote audio playback
