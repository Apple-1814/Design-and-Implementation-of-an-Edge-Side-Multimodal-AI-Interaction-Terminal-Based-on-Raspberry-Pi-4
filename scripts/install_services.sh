#!/usr/bin/env bash
# Install and enable systemd services for the edge AI terminal.
set -euo pipefail

ROOT="${ROOT:-$HOME/ai-terminal}"
if [ "$(id -u)" -eq 0 ] && [ "$HOME" = "/root" ]; then
  ROOT="/home/${SUDO_USER:-apple}/ai-terminal"
fi
if [ ! -d "$ROOT/pi/systemd" ]; then
  echo "systemd units not found: $ROOT/pi/systemd" >&2
  exit 1
fi

for port in 8080 8081 8000; do
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$port$"; then
    echo "port $port is already in use; stop the manual server first" >&2
    exit 1
  fi
done

sudo cp "$ROOT/pi/systemd/"*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable llama.service vlm.service ai-terminal.service
sudo systemctl restart llama.service vlm.service ai-terminal.service

sleep 8
systemctl --no-pager --full status llama.service vlm.service ai-terminal.service | sed -n '1,60p'
echo "--- api ---"
curl -sS --max-time 5 http://127.0.0.1:8000/api/info || true
echo
echo "services enabled; they will start on boot."
