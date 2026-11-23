#!/usr/bin/env bash
# Start LLM, VLM and FastAPI on the Raspberry Pi.
set -euo pipefail

ROOT="${ROOT:-$HOME/ai-terminal}"
LLAMA_DIR="${LLAMA_DIR:-$ROOT/llama.cpp}"
MODELS="${MODELS:-$ROOT/models}"
LOGS="${LOGS:-$ROOT/logs}"
mkdir -p "$LOGS"

export LD_LIBRARY_PATH="$LLAMA_DIR/build/bin:${LD_LIBRARY_PATH:-}"

echo "Starting LLM (Qwen2.5-1.5B) on 127.0.0.1:8080 ..."
nohup "$LLAMA_DIR/build/bin/llama-server" \
  -m "$MODELS/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  --host 127.0.0.1 --port 8080 -t 4 -c 2048 \
  > "$LOGS/llama_server.log" 2>&1 &
echo "LLM pid=$!"

echo "Starting VLM (SmolVLM-500M) on 127.0.0.1:8081 ..."
nohup "$LLAMA_DIR/build/bin/llama-server" \
  -m "$MODELS/SmolVLM-500M-Instruct-Q8_0.gguf" \
  --mmproj "$MODELS/mmproj-SmolVLM-500M-Instruct-Q8_0.gguf" \
  --host 127.0.0.1 --port 8081 -t 4 -c 2048 \
  > "$LOGS/vlm_server.log" 2>&1 &
echo "VLM pid=$!"

echo "Starting FastAPI on 0.0.0.0:8000 ..."
cd "$ROOT/pi"
. .venv/bin/activate
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  > "$LOGS/uvicorn.log" 2>&1 &
echo "API pid=$!"

sleep 4
echo "--- health ---"
curl -sS --max-time 5 http://127.0.0.1:8080/health || true
echo
curl -sS --max-time 5 http://127.0.0.1:8081/health || true
echo
curl -sS --max-time 5 http://127.0.0.1:8000/api/device/status || true
echo
echo "Open http://<raspberry-pi-ip>:8000/ in a browser."
