#!/usr/bin/env bash
# Stop the temporary Cloudflare quick tunnel started by start_tunnel.sh.
set -euo pipefail

if pgrep -f "[c]loudflared tunnel --url" >/dev/null 2>&1; then
  pkill -f "[c]loudflared tunnel --url" || true
  echo "cloudflared tunnel stopped"
else
  echo "no cloudflared tunnel running"
fi
