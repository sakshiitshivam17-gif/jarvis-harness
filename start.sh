#!/usr/bin/env bash
# Launch the J.A.R.V.I.S. harness locally and open it in Chrome.
set -euo pipefail

cd "$(dirname "$0")"
PORT="${JARVIS_PORT:-8765}"
URL="http://127.0.0.1:${PORT}/"

if [[ ! -x tools/piper/piper/piper || ! -x tools/cua-driver/cua-driver ]]; then
  echo "Fetching voice engine and driver on first run…"
  ./scripts/setup-assets.sh
fi
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c "import edge_tts" >/dev/null 2>&1; then
  .venv/bin/pip install -q -r requirements.txt
fi

if ! curl -sf -m 2 "${URL}api/health" >/dev/null 2>&1; then
  mkdir -p data
  setsid .venv/bin/python app.py >data/server.log 2>&1 < /dev/null &
  echo $! >data/server.pid
  for _ in {1..40}; do
    curl -sf -m 1 "${URL}api/health" >/dev/null 2>&1 && break
    sleep 0.25
  done
fi

echo "J.A.R.V.I.S. online: ${URL}"
echo "Click ENGAGE VOICE LINK once, then allow the microphone."

if flatpak info com.google.Chrome >/dev/null 2>&1; then
  setsid flatpak run com.google.Chrome "${URL}" >/dev/null 2>&1 < /dev/null &
elif command -v google-chrome-stable >/dev/null 2>&1; then
  setsid google-chrome-stable "${URL}" >/dev/null 2>&1 < /dev/null &
elif command -v chromium >/dev/null 2>&1; then
  setsid chromium "${URL}" >/dev/null 2>&1 < /dev/null &
else
  xdg-open "${URL}" >/dev/null 2>&1 &
fi
