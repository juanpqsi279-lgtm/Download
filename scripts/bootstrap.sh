#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
BIN_DIR="$ROOT_DIR/bin"
FFMPEG_BIN="$BIN_DIR/ffmpeg"
FFPROBE_BIN="$BIN_DIR/ffprobe"
DENO_BIN="$BIN_DIR/deno"

WEB_ONLY=0
WITH_DEV=0
for arg in "$@"; do
  case "$arg" in
    --web-only)
      WEB_ONLY=1
      ;;
    --dev)
      WITH_DEV=1
      ;;
    *)
      echo "Opción desconocida: $arg" >&2
      echo "Uso: $0 [--web-only] [--dev]" >&2
      exit 2
      ;;
  esac
done

RAW_ARCH="$(uname -m)"
case "$RAW_ARCH" in
  x86_64|amd64)
    ARCH="x86_64"
    FFMPEG_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz"
    DENO_URL="https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"
    ;;
  aarch64|arm64)
    ARCH="aarch64"
    FFMPEG_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
    DENO_URL="https://github.com/denoland/deno/releases/latest/download/deno-aarch64-unknown-linux-gnu.zip"
    ;;
  *)
    echo "Arquitectura Linux no soportada automáticamente: $RAW_ARCH" >&2
    exit 1
    ;;
esac

resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  if [ -x "$HOME/.local/bin/uv" ]; then
    echo "$HOME/.local/bin/uv"
    return 0
  fi
  if [ -x "$HOME/.cargo/bin/uv" ]; then
    echo "$HOME/.cargo/bin/uv"
    return 0
  fi
  return 1
}

download_file() {
  local url="$1"
  local dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fSL --retry 3 "$url" -o "$dest"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -q -O "$dest" "$url"
    return 0
  fi
  echo "Se requiere curl o wget para descargar dependencias." >&2
  exit 1
}

NEED_VENV=0
if [ ! -x "$VENV_PY" ]; then
  NEED_VENV=1
else
  if ! "$VENV_PY" -c "import fastapi, uvicorn, yt_dlp, httpx, webview" >/dev/null 2>&1; then
    NEED_VENV=1
  fi
  if [ "$WEB_ONLY" -eq 0 ] && ! "$VENV_PY" -c "import PyQt6.QtWebEngineWidgets" >/dev/null 2>&1; then
    NEED_VENV=1
  fi
  if [ "$WITH_DEV" -eq 1 ] && ! "$VENV_PY" -c "import pytest, PyInstaller, PIL" >/dev/null 2>&1; then
    NEED_VENV=1
  fi
fi

NEED_FFMPEG=0
if [ ! -x "$FFMPEG_BIN" ] || [ ! -x "$FFPROBE_BIN" ]; then
  NEED_FFMPEG=1
fi

NEED_DENO=0
if [ ! -x "$DENO_BIN" ]; then
  NEED_DENO=1
fi

if [ "$NEED_VENV" -eq 0 ] && [ "$NEED_FFMPEG" -eq 0 ] && [ "$NEED_DENO" -eq 0 ]; then
  echo "Entorno de !Download listo ($ARCH)."
  exit 0
fi

echo ""
echo "=========================================================="
echo "  Configurando !Download para Linux ($ARCH)"
echo "=========================================================="
echo ""

cd "$ROOT_DIR"

if [ "$NEED_VENV" -eq 1 ]; then
  UV_BIN="$(resolve_uv || true)"
  if [ -z "$UV_BIN" ]; then
    echo "[1/3] Instalando uv (gestor de Python)..."
    if command -v curl >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://astral.sh/uv/install.sh | sh
    else
      echo "Se requiere curl o wget para instalar uv." >&2
      exit 1
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    UV_BIN="$(resolve_uv || true)"
    if [ -z "$UV_BIN" ]; then
      echo "No se pudo encontrar uv después de instalarlo." >&2
      exit 1
    fi
  fi

  if [ ! -x "$VENV_PY" ]; then
    echo "[1/3] Creando entorno Python 3.13..."
    "$UV_BIN" venv --python 3.13 "$VENV_DIR"
  fi

  EXTRAS=""
  if [ "$WEB_ONLY" -eq 0 ] && [ "$WITH_DEV" -eq 1 ]; then
    EXTRAS="[linux-desktop,dev]"
  elif [ "$WEB_ONLY" -eq 0 ]; then
    EXTRAS="[linux-desktop]"
  elif [ "$WITH_DEV" -eq 1 ]; then
    EXTRAS="[dev]"
  fi

  echo "[2/3] Instalando dependencias de !Download${EXTRAS}..."
  "$UV_BIN" pip install --python "$VENV_PY" -e ".${EXTRAS}"
fi

if [ "$NEED_FFMPEG" -eq 1 ] || [ "$NEED_DENO" -eq 1 ]; then
  mkdir -p "$BIN_DIR"
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/exclaim-dl-setup-XXXXXX")"
  trap 'rm -rf "$TMP_DIR"' EXIT

  if [ "$NEED_FFMPEG" -eq 1 ]; then
    echo "[3/3] Descargando FFmpeg y FFprobe portables ($ARCH)..."
    FFMPEG_ARCHIVE="$TMP_DIR/ffmpeg.tar.xz"
    download_file "$FFMPEG_URL" "$FFMPEG_ARCHIVE"
    "$VENV_PY" - "$FFMPEG_ARCHIVE" "$FFMPEG_BIN" "$FFPROBE_BIN" <<'PYEOF'
import os
import shutil
import sys
import tarfile
from pathlib import Path

archive_path = Path(sys.argv[1])
targets = {"ffmpeg": Path(sys.argv[2]), "ffprobe": Path(sys.argv[3])}
found = set()

with tarfile.open(archive_path, "r:xz") as tf:
    for member in tf.getmembers():
        if not member.isfile():
            continue
        name = Path(member.name).name
        if name in targets and name not in found:
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, targets[name].open("wb") as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(targets[name], 0o755)
            found.add(name)

missing = set(targets.keys()) - found
if missing:
    raise SystemExit(f"Faltan binarios en el archivo FFmpeg: {sorted(missing)}")
PYEOF
  fi

  if [ "$NEED_DENO" -eq 1 ]; then
    echo "[3/3] Descargando Deno portable ($ARCH)..."
    DENO_ARCHIVE="$TMP_DIR/deno.zip"
    download_file "$DENO_URL" "$DENO_ARCHIVE"
    "$VENV_PY" - "$DENO_ARCHIVE" "$DENO_BIN" <<'PYEOF'
import os
import shutil
import sys
import zipfile
from pathlib import Path

archive_path = Path(sys.argv[1])
dest_path = Path(sys.argv[2])

with zipfile.ZipFile(archive_path, "r") as zf:
    for info in zf.infolist():
        if not info.is_dir() and Path(info.filename).name == "deno":
            with zf.open(info, "r") as src, dest_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(dest_path, 0o755)
            break
    else:
        raise SystemExit("No se encontró el binario deno en el archivo descargado.")
PYEOF
  fi
fi

echo ""
echo "!Download quedó configurado correctamente en Linux."
