# !Download

Aplicación de escritorio y web local desarrollada por **Juan Corporation** con estética **iOS 27 Liquid Glass** (modo oscuro y modo claro, animaciones fluidas e inspector completo de metadatos) para descargar contenido multimedia en múltiples calidades de **video** (hasta 4K/8K en MP4, MKV o WebM) o **solo audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).

## Descargar desde Releases (Windows, Linux y Android)

Si solo quieres usar `!Download` sin instalar herramientas ni compilar nada, descarga la última versión todo incluido desde **GitHub Releases**:

👉 **[Descargar última versión (Releases)](https://github.com/juanpqsi279-lgtm/Download/releases/latest)**

### Windows
- **`Download-Setup-v1.2.0.exe`**: instalador clásico para Windows (crea accesos directos y soporta auto-actualizaciones).
- **`Download-Portable-v1.2.0.zip`**: versión portable (descomprimir y abrir `!Download.exe`).

### Linux (`x86_64` / `amd64`)
- **`Download-v1.2.0-linux-x86_64.AppImage`**: ejecutable portable universal (`chmod +x` y ejecutar; soporta auto-actualizaciones).
- **`Download-v1.2.0-linux-amd64.deb`**: paquete para Debian, Ubuntu, Linux Mint y Pop!_OS (`sudo apt install ./Download-v1.2.0-linux-amd64.deb`).
- **`Download-Portable-v1.2.0-linux-x86_64.tar.gz`**: archivo portable (descomprimir y ejecutar `./exclaim-download/exclaim-download`; incluye `./exclaim-download/install-desktop.sh` para crear acceso directo y soporta auto-actualizaciones).

### Android (`.apk` todo incluido)
- **`Download-v1.2.0-android-arm64.apk`**: recomendado para la mayoría de teléfonos Android modernos (`arm64-v8a`, más ligero).
- **`Download-v1.2.0-android-universal.apk`**: compatible con cualquier arquitectura Android (`arm64-v8a`, `armeabi-v7a`, `x86_64`).
- Incluye motor `yt-dlp` + `FFmpeg` embebido, guardado directo en `Download/!Download/`, notificaciones de progreso, opción **Compartir → `!Download`** desde YouTube/TikTok/Instagram/X y actualización del motor y APK desde Ajustes.

---

## Ejecutar desde el código fuente (todo automático)

### Windows

Haz doble clic en:

- **[`!Download-Desktop.bat`](!Download-Desktop.bat)** — abre `!Download` en su propia ventana nativa de escritorio (sin abrir navegador).
- **[`start.bat`](start.bat)** o **[`start.ps1`](start.ps1)** — inicia el servidor local en `http://127.0.0.1:8000`.

> En la primera ejecución, [scripts/bootstrap.ps1](scripts/bootstrap.ps1) detecta automáticamente si falta `.venv` o `bin/` e instala `uv`, Python 3.13, dependencias, `FFmpeg`, `FFprobe` y `Deno` de forma automática.

> **Nota sobre Windows 11 Smart App Control:** en equipos con Control de aplicaciones / Smart App Control activo, Windows puede bloquear ejecutables `.exe` sin firma digital (*Authenticode*). En ese caso, usa `!Download-Desktop.bat` para abrir exactamente la misma ventana nativa.

### Linux

Ejecuta en una terminal:

- **[`./download-desktop.sh`](download-desktop.sh)** — abre `!Download` en su propia ventana nativa de escritorio (`PyQt6-WebEngine`).
- **[`./start.sh`](start.sh)** — inicia el servidor web local en `http://127.0.0.1:8000` (solo requiere modo web, sin Qt).

> En la primera ejecución, [scripts/bootstrap.sh](scripts/bootstrap.sh) detecta automáticamente si falta `.venv` o `bin/` e instala `uv`, Python 3.13, dependencias, `FFmpeg`, `FFprobe` y `Deno` de forma automática.

## Sistema de actualizaciones en 2 niveles

1. **Actualización del motor (`yt-dlp`):** dentro de **Ajustes** en `!Download`, pulsa **Actualizar motor** para descargar el paquete zipapp oficial más reciente de `yt-dlp` sin recompilar la aplicación.
2. **Actualizaciones de `!Download`:** al abrir la app, consulta `https://api.github.com/repos/juanpqsi279-lgtm/Download/releases/latest` y permite descargar e instalar nuevas versiones publicadas en GitHub Releases (en Windows `.exe`/`.zip` y en Linux `.AppImage`/`.tar.gz`).

## Cómo compilar el ejecutable desde cero

### Windows

```powershell
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.\.venv\Scripts\python.exe scripts\generate_icon.py
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean build.spec
```

### Linux

```bash
./scripts/bootstrap.sh --dev
./scripts/build_linux_packages.sh
```

> El script [scripts/build_linux_packages.sh](scripts/build_linux_packages.sh) compila el binario con PyInstaller, valida `--self-check --check-gui` y genera los paquetes `.AppImage`, `.deb` y `.tar.gz` en `dist/`.

### Android

Requiere JDK 17, Android SDK (API 35) y Gradle 8.11+:

```bash
gradle -p android testDebugUnitTest
gradle -p android assembleRelease
```

> El flujo de GitHub Actions compila automáticamente `Download-v*-android-arm64.apk` y `Download-v*-android-universal.apk` en cada release.

## Publicar una nueva versión en GitHub Releases

El flujo [release.yml](.github/workflows/release.yml) ejecuta las pruebas, compila los ejecutables y paquetes de **Windows**, **Linux** y **Android**, verifica `--self-check` y publica todos los archivos automáticamente al subir una etiqueta `v*`:

```bash
git tag v1.0.1 && git push origin v1.0.1
```
