#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_PY="$ROOT_DIR/.venv/bin/python"
PYINSTALLER="$ROOT_DIR/.venv/bin/pyinstaller"

if [ ! -x "$VENV_PY" ] || [ ! -x "$PYINSTALLER" ]; then
  echo "Falta .venv con PyInstaller. Ejecuta primero: ./scripts/bootstrap.sh --dev" >&2
  exit 1
fi

for tool in ffmpeg ffprobe deno; do
  if [ ! -x "$ROOT_DIR/bin/$tool" ]; then
    echo "Falta bin/$tool. Ejecuta primero: ./scripts/bootstrap.sh --dev" >&2
    exit 1
  fi
done

TAG="${1:-}"
if [ -z "$TAG" ]; then
  if [[ "${GITHUB_REF_NAME:-}" == v* ]]; then
    TAG="$GITHUB_REF_NAME"
  else
    APP_VER="$("$VENV_PY" -c "from app.config import APP_VERSION; print(APP_VERSION)")"
    TAG="v${APP_VER}"
  fi
fi
DEB_VERSION="${TAG#v}"

RAW_ARCH="$(uname -m)"
case "$RAW_ARCH" in
  x86_64|amd64)
    ARCH="x86_64"
    DEB_ARCH="amd64"
    ;;
  aarch64|arm64)
    ARCH="aarch64"
    DEB_ARCH="arm64"
    ;;
  *)
    echo "Arquitectura no soportada para empaquetado Linux: $RAW_ARCH" >&2
    exit 1
    ;;
esac

if [ ! -f "$ROOT_DIR/static/icon.png" ]; then
  "$VENV_PY" "$ROOT_DIR/scripts/generate_icon.py"
fi

echo "[1/5] Compilando binario con PyInstaller ($ARCH)..."
"$PYINSTALLER" --noconfirm --clean "$ROOT_DIR/build.spec"

DIST_BUNDLE="$ROOT_DIR/dist/exclaim-download"
if [ ! -x "$DIST_BUNDLE/exclaim-download" ]; then
  echo "No se generó el ejecutable esperado en $DIST_BUNDLE/exclaim-download" >&2
  exit 1
fi

for tool in ffmpeg ffprobe deno; do
  for candidate in "$DIST_BUNDLE/_internal/bin/$tool" "$DIST_BUNDLE/bin/$tool"; do
    if [ -f "$candidate" ]; then
      chmod 0755 "$candidate"
    fi
  done
done

QT_WEBENGINE_PROC="$(find "$DIST_BUNDLE" -name QtWebEngineProcess -type f | head -n 1 || true)"
if [ -z "$QT_WEBENGINE_PROC" ]; then
  echo "Error: QtWebEngineProcess no quedó incluido en $DIST_BUNDLE" >&2
  exit 1
fi
chmod 0755 "$QT_WEBENGINE_PROC"

echo "[2/5] Verificando --self-check --check-gui del ejecutable compilado..."
"$DIST_BUNDLE/exclaim-download" --self-check --check-gui

# ------------------------------------------------------------------
# 1) Portable .tar.gz
# ------------------------------------------------------------------
echo "[3/5] Generando archivo portable .tar.gz..."
TAR_OUT="$ROOT_DIR/dist/Download-Portable-${TAG}-linux-${ARCH}.tar.gz"
TAR_STAGE="$ROOT_DIR/build/tar-pkg"
rm -rf "$TAR_STAGE"
mkdir -p "$TAR_STAGE/exclaim-download"
cp -a "$DIST_BUNDLE/." "$TAR_STAGE/exclaim-download/"
cp "$ROOT_DIR/static/icon.png" "$TAR_STAGE/exclaim-download/exclaim-download.png"

cat > "$TAR_STAGE/exclaim-download/install-desktop.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/512x512/apps"

mkdir -p "$APPS_DIR" "$ICON_DIR"
cp "$APP_DIR/exclaim-download.png" "$ICON_DIR/exclaim-download.png"

cat > "$APPS_DIR/exclaim-download.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=!Download
GenericName=Multimedia Downloader
Comment=Descarga video y audio con estética Liquid Glass
Exec="$APP_DIR/exclaim-download" %U
Icon=exclaim-download
Terminal=false
Categories=AudioVideo;Video;Audio;Network;Utility;
Keywords=youtube;video;audio;downloader;yt-dlp;ffmpeg;
StartupNotify=true
StartupWMClass=exclaim-download
DESKTOP

chmod 0644 "$APPS_DIR/exclaim-download.desktop"
update-desktop-database -q "$APPS_DIR" 2>/dev/null || true
gtk-update-icon-cache -q -t -f "$DATA_HOME/icons/hicolor" 2>/dev/null || true
echo "Acceso directo instalado en $APPS_DIR/exclaim-download.desktop"
EOF

cat > "$TAR_STAGE/exclaim-download/uninstall-desktop.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$DATA_HOME/applications/exclaim-download.desktop"
rm -f "$DATA_HOME/icons/hicolor/512x512/apps/exclaim-download.png"
update-desktop-database -q "$DATA_HOME/applications" 2>/dev/null || true
gtk-update-icon-cache -q -t -f "$DATA_HOME/icons/hicolor" 2>/dev/null || true
echo "Acceso directo eliminado."
EOF

chmod 0755 "$TAR_STAGE/exclaim-download/install-desktop.sh" "$TAR_STAGE/exclaim-download/uninstall-desktop.sh"
tar -C "$TAR_STAGE" -czf "$TAR_OUT" exclaim-download

# ------------------------------------------------------------------
# 2) .deb package
# ------------------------------------------------------------------
if command -v dpkg-deb >/dev/null 2>&1; then
  echo "[4/5] Generando paquete .deb ($DEB_ARCH)..."
  DEB_OUT="$ROOT_DIR/dist/Download-${TAG}-linux-${DEB_ARCH}.deb"
  DEB_STAGE="$ROOT_DIR/build/deb-pkg"
  rm -rf "$DEB_STAGE"
  mkdir -p \
    "$DEB_STAGE/DEBIAN" \
    "$DEB_STAGE/opt/exclaim-download" \
    "$DEB_STAGE/usr/bin" \
    "$DEB_STAGE/usr/share/applications" \
    "$DEB_STAGE/usr/share/icons/hicolor/512x512/apps"

  cp -a "$DIST_BUNDLE/." "$DEB_STAGE/opt/exclaim-download/"
  ln -s /opt/exclaim-download/exclaim-download "$DEB_STAGE/usr/bin/exclaim-download"
  cp "$ROOT_DIR/packaging/linux/exclaim-download.desktop" "$DEB_STAGE/usr/share/applications/exclaim-download.desktop"
  cp "$ROOT_DIR/static/icon.png" "$DEB_STAGE/usr/share/icons/hicolor/512x512/apps/exclaim-download.png"
  chmod 0644 "$DEB_STAGE/usr/share/applications/exclaim-download.desktop"
  chmod 0644 "$DEB_STAGE/usr/share/icons/hicolor/512x512/apps/exclaim-download.png"

  INSTALLED_SIZE="$(du -sk "$DEB_STAGE" | cut -f1)"
  cat > "$DEB_STAGE/DEBIAN/control" <<EOF
Package: exclaim-download
Version: ${DEB_VERSION}
Section: utils
Priority: optional
Architecture: ${DEB_ARCH}
Maintainer: Juan Corporation <https://github.com/juanpqsi279-lgtm/Download>
Installed-Size: ${INSTALLED_SIZE}
Depends: libc6, libegl1, libgl1, libgbm1, libnss3, libnspr4, libdbus-1-3, libfontconfig1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xfixes0, libxcomposite1, libxdamage1, libxrandr2, libxtst6, libdrm2, libasound2t64 | libasound2, libatk1.0-0t64 | libatk1.0-0, libatk-bridge2.0-0t64 | libatk-bridge2.0-0, libcups2t64 | libcups2, xdg-utils
Homepage: https://github.com/juanpqsi279-lgtm/Download
Description: !Download multimedia downloader by Juan Corporation
 Aplicacion de escritorio con estetica Liquid Glass para descargar video y audio.
EOF
  chmod 0644 "$DEB_STAGE/DEBIAN/control"

  cat > "$DEB_STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
EOF
  cat > "$DEB_STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
EOF
  chmod 0755 "$DEB_STAGE/DEBIAN" "$DEB_STAGE/DEBIAN/postinst" "$DEB_STAGE/DEBIAN/postrm"

  dpkg-deb --build --root-owner-group "$DEB_STAGE" "$DEB_OUT"
else
  echo "[4/5] dpkg-deb no está disponible; omitiendo paquete .deb."
fi

# ------------------------------------------------------------------
# 3) .AppImage
# ------------------------------------------------------------------
echo "[5/5] Generando .AppImage ($ARCH)..."
TOOLS_DIR="$ROOT_DIR/build/tools"
mkdir -p "$TOOLS_DIR"
APPIMAGETOOL=""
if command -v appimagetool >/dev/null 2>&1; then
  APPIMAGETOOL="$(command -v appimagetool)"
else
  CACHED_TOOL="$TOOLS_DIR/appimagetool-${ARCH}.AppImage"
  if [ ! -x "$CACHED_TOOL" ]; then
    TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    if command -v curl >/dev/null 2>&1; then
      curl -fSL --retry 3 "$TOOL_URL" -o "$CACHED_TOOL"
    elif command -v wget >/dev/null 2>&1; then
      wget -q -O "$CACHED_TOOL" "$TOOL_URL"
    else
      echo "Se requiere curl o wget para descargar appimagetool." >&2
      exit 1
    fi
    chmod 0755 "$CACHED_TOOL"
  fi
  APPIMAGETOOL="$CACHED_TOOL"
fi

APPDIR="$ROOT_DIR/build/AppDir"
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/lib/exclaim-download" \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/icons/hicolor/512x512/apps"

cp -a "$DIST_BUNDLE/." "$APPDIR/usr/lib/exclaim-download/"
ln -s ../lib/exclaim-download/exclaim-download "$APPDIR/usr/bin/exclaim-download"
cp "$ROOT_DIR/static/icon.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/exclaim-download.png"
cp "$ROOT_DIR/static/icon.png" "$APPDIR/exclaim-download.png"
cp "$ROOT_DIR/static/icon.png" "$APPDIR/.DirIcon"
cp "$ROOT_DIR/packaging/linux/exclaim-download.desktop" "$APPDIR/exclaim-download.desktop"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PATH="$HERE/usr/lib/exclaim-download/_internal/bin:$PATH"
export QTWEBENGINE_DISABLE_SANDBOX="${QTWEBENGINE_DISABLE_SANDBOX:-1}"
exec "$HERE/usr/lib/exclaim-download/exclaim-download" "$@"
EOF
chmod 0755 "$APPDIR/AppRun"

APPIMAGE_OUT="$ROOT_DIR/dist/Download-${TAG}-linux-${ARCH}.AppImage"
rm -f "$APPIMAGE_OUT"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" --no-appstream "$APPDIR" "$APPIMAGE_OUT"
chmod 0755 "$APPIMAGE_OUT"

echo "Verificando .AppImage..."
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE_OUT" --self-check --check-gui

echo ""
echo "Artefactos Linux generados en dist/:"
ls -lh "$ROOT_DIR/dist"/Download*"${TAG}"* 2>/dev/null || ls -lh "$ROOT_DIR/dist"
