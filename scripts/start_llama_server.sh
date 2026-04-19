#!/usr/bin/env bash
# Start llama.cpp HTTP server with Gemma 4 E4B
# Called by systemd ExecStartPre or manually

ROBOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="$ROBOT_DIR/models/gemma-4-e4b-it-q4_k_m.gguf"

echo "Starting llama.cpp server..."
echo "  Model: $MODEL"

llama-server \
    -m "$MODEL" \
    --host 127.0.0.1 \
    --port 8080 \
    -c 4096 \
    -t 4 \
    --n-predict 256 \
    --no-mmap &

LLAMA_PID=$!
echo "  PID: $LLAMA_PID"

# Wait for server to be ready (model loading from microSD takes ~30s)
echo "  Waiting for model to load..."
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "  ✓ llama.cpp server ready (${i}s)"
        exit 0
    fi
    sleep 1
done

echo "  ✗ llama.cpp server failed to start within 60s"
exit 1
