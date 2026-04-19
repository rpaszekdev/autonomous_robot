#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Conversational Robot — Full Setup Script
# Raspberry Pi 5 (8GB) · Gemma 4 E4B · OpenClaw · llama.cpp · Piper TTS
# Run: chmod +x scripts/setup.sh && ./scripts/setup.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROBOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="$ROBOT_DIR/models"
VENV_DIR="$ROBOT_DIR/.venv"

echo "══════════════════════════════════════════════════"
echo "  Conversational Robot — Setup"
echo "══════════════════════════════════════════════════"

# ── 1. System packages ───────────────────────────────────────
echo ""
echo "[1/7] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    build-essential cmake git \
    python3 python3-pip python3-venv \
    portaudio19-dev libsndfile1 \
    libcamera-dev libcamera-apps \
    aplay alsa-utils \
    wget curl jq

# ── 2. Build llama.cpp from source (ARM NEON optimised) ──────
echo ""
echo "[2/7] Building llama.cpp..."
if [ ! -d "$ROBOT_DIR/llama.cpp" ]; then
    git clone https://github.com/ggml-org/llama.cpp.git "$ROBOT_DIR/llama.cpp"
fi
cd "$ROBOT_DIR/llama.cpp"
git pull --ff-only || true
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CPU_ARM_NEON=ON
cmake --build build --config Release -j$(nproc)
sudo cmake --install build
cd "$ROBOT_DIR"
echo "  ✓ llama.cpp built and installed"

# ── 3. Download Gemma 4 E4B Q4_K_M GGUF ─────────────────────
echo ""
echo "[3/7] Downloading Gemma 4 E4B model (~4 GB)..."
mkdir -p "$MODELS_DIR"
MODEL_FILE="$MODELS_DIR/gemma-4-e4b-it-q4_k_m.gguf"
if [ ! -f "$MODEL_FILE" ]; then
    # Download from Hugging Face (bartowski's quantised builds)
    wget -c -O "$MODEL_FILE" \
        "https://huggingface.co/bartowski/google_gemma-4-4b-it-GGUF/resolve/main/google_gemma-4-4b-it-Q4_K_M.gguf"
    echo "  ✓ Model downloaded to $MODEL_FILE"
else
    echo "  ✓ Model already exists at $MODEL_FILE"
fi

# ── 4. Install Piper TTS ─────────────────────────────────────
echo ""
echo "[4/7] Installing Piper TTS..."
PIPER_DIR="$ROBOT_DIR/piper"
if [ ! -d "$PIPER_DIR" ]; then
    mkdir -p "$PIPER_DIR"
    PIPER_RELEASE="https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz"
    wget -qO- "$PIPER_RELEASE" | tar xz -C "$PIPER_DIR" --strip-components=1
fi
# Download default English voice
VOICE_DIR="$ROBOT_DIR/models/piper-voices"
mkdir -p "$VOICE_DIR"
if [ ! -f "$VOICE_DIR/en_US-lessac-medium.onnx" ]; then
    wget -q -O "$VOICE_DIR/en_US-lessac-medium.onnx" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
    wget -q -O "$VOICE_DIR/en_US-lessac-medium.onnx.json" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
fi
echo "  ✓ Piper TTS installed with en_US-lessac-medium voice"

# ── 5. Python virtual environment + dependencies ─────────────
echo ""
echo "[5/7] Setting up Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$ROBOT_DIR/requirements.txt"
echo "  ✓ Python environment ready"

# ── 6. Download openWakeWord model ───────────────────────────
echo ""
echo "[6/7] Downloading wake word model..."
WAKE_DIR="$ROBOT_DIR/models/wake-word"
mkdir -p "$WAKE_DIR"
if [ ! -f "$WAKE_DIR/hey_robot.onnx" ]; then
    # Use openWakeWord's built-in 'hey jarvis' as base; rename for our trigger
    python3 -c "
import openwakeword
openwakeword.utils.download_models(target_directory='$WAKE_DIR')
print('Wake word models downloaded')
"
fi
echo "  ✓ Wake word models ready"

# ── 7. Generate acknowledgment tone ──────────────────────────
echo ""
echo "[7/7] Generating acknowledgment tone..."
ASSETS_DIR="$ROBOT_DIR/assets"
mkdir -p "$ASSETS_DIR"
if [ ! -f "$ASSETS_DIR/ack_tone.wav" ]; then
    python3 -c "
import numpy as np
import wave
sr = 16000
duration = 0.2
t = np.linspace(0, duration, int(sr * duration), endpoint=False)
# Pleasant two-tone chirp (C5 → E5)
tone = 0.5 * np.sin(2 * np.pi * 523.25 * t)
tone[len(t)//2:] = 0.5 * np.sin(2 * np.pi * 659.25 * t[len(t)//2:])
# Fade in/out
fade = int(sr * 0.01)
tone[:fade] *= np.linspace(0, 1, fade)
tone[-fade:] *= np.linspace(1, 0, fade)
pcm = (tone * 32767).astype(np.int16)
with wave.open('$ASSETS_DIR/ack_tone.wav', 'w') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(pcm.tobytes())
print('Generated ack_tone.wav')
"
fi
echo "  ✓ Acknowledgment tone ready"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Model:   $MODEL_FILE"
echo "  Piper:   $PIPER_DIR"
echo "  Venv:    $VENV_DIR"
echo ""
echo "  To start the robot:"
echo "    source .venv/bin/activate"
echo "    python openclaw/main.py"
echo ""
echo "  Or install the systemd service:"
echo "    sudo cp scripts/robot.service /etc/systemd/system/"
echo "    sudo systemctl enable --now robot"
echo "══════════════════════════════════════════════════"
