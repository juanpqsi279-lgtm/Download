#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venv/bin/python" ] || [ ! -x "bin/ffmpeg" ] || [ ! -x "bin/ffprobe" ] || [ ! -x "bin/deno" ]; then
  bash "$ROOT_DIR/scripts/bootstrap.sh" --web-only
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
URL="http://${HOST}:${PORT}"

echo "Iniciando !Download (Juan Corporation) en ${URL} ..."

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  if command -v xdg-open >/dev/null 2>&1; then
    (sleep 2 && xdg-open "$URL" >/dev/null 2>&1) &
  elif command -v gio >/dev/null 2>&1; then
    (sleep 2 && gio open "$URL" >/dev/null 2>&1) &
  fi
fi

exec "$ROOT_DIR/.venv/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
