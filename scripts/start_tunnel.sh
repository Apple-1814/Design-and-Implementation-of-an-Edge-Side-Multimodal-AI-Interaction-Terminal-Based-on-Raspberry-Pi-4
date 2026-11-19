#!/usr/bin/env bash
# Start a temporary Cloudflare quick tunnel to the local FastAPI app.
# Run on the Raspberry Pi from the repository root.
set -euo pipefail

BIN="${CLOUDFLARED_BIN:-$HOME/ai-terminal/bin/cloudflared}"
LOG="${CLOUDFLARED_LOG:-$HOME/ai-terminal/logs/cloudflared.log}"
URL="${LOCAL_URL:-http://127.0.0.1:8000}"

if [[ ! -x "$BIN" ]]; then
  echo "cloudflared not found or not executable: $BIN" >&2
  echo "Download cloudflared-linux-arm64 to that path and chmod +x." >&2
  exit 2
fi

if pgrep -f "[c]loudflared tunnel --url" >/dev/null 2>&1; then
  echo "A cloudflared tunnel is already running:"
  pgrep -af "[c]loudflared tunnel --url"
  grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1 || true
  exit 0
fi

mkdir -p "$(dirname "$LOG")"
setsid "$BIN" tunnel --url "$URL" --no-autoupdate --protocol http2 \
  >"$LOG" 2>&1 </dev/null &

for _ in $(seq 1 30); do
  sleep 1
  PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | head -1 || true)"
  if [[ -n "$PUBLIC_URL" ]]; then
    echo "Public URL: $PUBLIC_URL"
    echo "Log: $LOG"
    exit 0
  fi
done

echo "Tunnel did not produce a URL within 30s; see $LOG" >&2
tail -20 "$LOG" >&2 || true
exit 1
