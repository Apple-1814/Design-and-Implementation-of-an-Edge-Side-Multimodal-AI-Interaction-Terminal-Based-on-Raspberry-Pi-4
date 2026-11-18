#!/usr/bin/env bash
# Start llama-server for SmolVLM-500M (multimodal) on the Raspberry Pi.
set -euo pipefail

LLAMA_DIR="${LLAMA_DIR:-$HOME/ai-terminal/llama.cpp}"
MODEL="${MODEL:-$HOME/ai-terminal/models/SmolVLM-500M-Instruct-Q8_0.gguf}"
MMPROJ="${MMPROJ:-$HOME/ai-terminal/models/mmproj-SmolVLM-500M-Instruct-Q8_0.gguf}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8081}"
THREADS="${THREADS:-4}"
CTX="${CTX:-2048}"

exec "$LLAMA_DIR/build/bin/llama-server" \
  -m "$MODEL" --mmproj "$MMPROJ" \
  --host "$HOST" --port "$PORT" \
  -t "$THREADS" -c "$CTX"
