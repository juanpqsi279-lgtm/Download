#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

NEED_SETUP=0
if [ ! -x ".venv/bin/python" ] || [ ! -x "bin/ffmpeg" ] || [ ! -x "bin/ffprobe" ] || [ ! -x "bin/deno" ]; then
  NEED_SETUP=1
elif ! ".venv/bin/python" -c "import PyQt6.QtWebEngineWidgets" >/dev/null 2>&1; then
  NEED_SETUP=1
fi

if [ "$NEED_SETUP" -eq 1 ]; then
  bash "$ROOT_DIR/scripts/bootstrap.sh"
fi

exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/desktop_main.py" "$@"
