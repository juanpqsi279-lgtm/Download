# !Download

Aplicación de escritorio y web local desarrollada por **Juan Corporation** con estética **iOS 27 Liquid Glass** (modo oscuro y modo claro, animaciones fluidas e inspector completo de metadatos) para descargar contenido multimedia en múltiples calidades de **video** (hasta 4K/8K en MP4, MKV o WebM) o **solo audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).

## Descargar desde Releases (Windows, Linux, Android e iPhone)

Si solo quieres usar `!Download` sin instalar herramientas ni compilar nada, descarga la última versión todo incluido desde **GitHub Releases**:

👉 **[Descargar última versión (Releases)](https://github.com/juanpqsi279-lgtm/Download/releases/latest)**

### Windows
- **`Download-Setup-v1.3.0.exe`**: instalador clásico para Windows (crea accesos directos y soporta auto-actualizaciones).
- **`Download-Portable-v1.3.0.zip`**: versión portable (descomprimir y abrir `!Download.exe`).
  > **Importante (Error 4551 / Windows Smart App Control):** si tu Windows 11 tiene *Control de aplicaciones inteligente (Smart App Control)* activado, bloqueará cualquier `.exe` descargado que no cuente con certificado digital (*Authenticode*). En ese equipo usa **[`!Download-Desktop.bat`](!Download-Desktop.bat)** (corre sobre Python firmado), o agrega secretos `WINDOWS_CERT_PFX_BASE64` y `WINDOWS_CERT_PASSWORD` en GitHub para firmar el `.exe` automáticamente en cada release.

### Linux (`x86_64` / `amd64`)
- **`Download-v1.3.0-linux-x86_64.AppImage`**: ejecutable portable universal (`chmod +x` y ejecutar; soporta auto-actualizaciones).
- **`Download-v1.3.0-linux-amd64.deb`**: paquete para Debian, Ubuntu, Linux Mint y Pop!_OS (`sudo apt install ./Download-v1.3.0-linux-amd64.deb`).
- **`Download-Portable-v1.3.0-linux-x86_64.tar.gz`**: archivo portable (descomprimir y ejecutar `./exclaim-download/exclaim-download`; incluye `./exclaim-download/install-desktop.sh` para crear acceso directo y soporta auto-actualizaciones).

### Android (`.apk` todo incluido)
- **`Download-v1.3.0-android-arm64.apk`**: recomendado para la mayoría de teléfonos Android modernos (`arm64-v8a`, más ligero).
- **`Download-v1.3.0-android-universal.apk`**: compatible con cualquier arquitectura Android (`arm64-v8a`, `armeabi-v7a`, `x86_64`).
- Incluye motor `yt-dlp` + `FFmpeg` embebido, guardado directo en `Download/!Download/`, notificaciones de progreso, opción **Compartir → `!Download`** desde YouTube/TikTok/Instagram/X y actualización del motor y APK desde Ajustes.

### iPhone / iPad (`Download-v1.3.0-ios.ipa`)
- **`Download-v1.3.0-ios.ipa`**: app iOS nativa con UI Liquid Glass (`WKWebView`), Python 3.14 + `yt-dlp` embebido, **Apple JavaScriptCore** para retos de YouTube y **AVFoundation** para unir video + audio en MP4 y guardar directo en **Archivos → En mi iPhone → `!Download`** (con botón para guardar en Fototeca/AirDrop).
- **Cómo instalar el `.ipa` en iPhone sin App Store:** usa **[AltStore](https://altstore.io/)**, **[SideStore](https://sidestore.io/)**, **Sideloadly** o **TrollStore**.
- **Alternativa sin instalar `.ipa` (PWA en Safari):** corre `!Download` en tu PC/Mac en la red local o por Cloudflare Tunnel, ábrelo en **Safari** y pulsa **Compartir → Añadir a pantalla de inicio**.

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

### iPhone / iOS

Requiere macOS con Xcode 16+ y `xcodegen`:

```bash
mkdir -p ios/App/WebAssets/static
cp static/index.html static/styles.css static/app.js static/icon.png static/manifest.webmanifest ios/App/WebAssets/static/
cd ios && xcodegen generate
```

## Publicar una nueva versión en GitHub Releases

El flujo [release.yml](.github/workflows/release.yml) ejecuta las pruebas, compila los ejecutables y paquetes de **Windows**, **Linux**, **Android** e **iOS**, verifica `--self-check` y publica todos los archivos automáticamente al subir una etiqueta `v*`:

```bash
git tag v1.3.0 && git push origin v1.3.0
```
