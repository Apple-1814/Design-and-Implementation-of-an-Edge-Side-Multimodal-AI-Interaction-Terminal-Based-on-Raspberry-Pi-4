#!/usr/bin/env bash
# Start llama-server for Qwen2.5-0.5B on the Raspberry Pi.
set -euo pipefail

LLAMA_DIR="${LLAMA_DIR:-$HOME/ai-terminal/llama.cpp}"
MODEL="${MODEL:-$HOME/ai-terminal/models/qwen2.5-0.5b-instruct-q4_k_m.gguf}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
THREADS="${THREADS:-4}"
CTX="${CTX:-2048}"

exec "$LLAMA_DIR/build/bin/llama-server" \
  -m "$MODEL" \
  --host "$HOST" --port "$PORT" \
  -t "$THREADS" -c "$CTX"
