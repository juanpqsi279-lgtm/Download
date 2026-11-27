# !Download

Aplicación de escritorio, móvil y web local desarrollada por **Juan Corporation** con estética **iOS 27 Liquid Glass** (modo oscuro y modo claro, animaciones fluidas e inspector completo de metadatos) para descargar contenido multimedia en múltiples calidades de **video** (hasta 4K/8K en MP4, MKV o WebM) o **solo audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).

👉 **[Descargar última versión todo incluido (GitHub Releases)](https://github.com/juanpqsi279-lgtm/Download/releases/latest)**

---

## Guía de instalación por sistema operativo

### Windows (10 / 11)

- **Opción 1 — Instalador (`Download-Setup-v1.6.0.exe`):**
  1. Descarga **`Download-Setup-v1.6.0.exe`** desde [Releases](https://github.com/juanpqsi279-lgtm/Download/releases/latest).
  2. Ejecuta el instalador para crear los accesos directos y activar auto-actualizaciones.
- **Opción 2 — Portable (`Download-Portable-v1.6.0.zip`):**
  1. Descarga y descomprime **`Download-Portable-v1.6.0.zip`**.
  2. Abre **`!Download.exe`**.
- **Opción 3 — Ejecutar desde código fuente (recomendado si Windows bloquea el `.exe`):**
  1. Clona o descarga este repositorio.
  2. Haz doble clic en **[`!Download-Desktop.bat`](!Download-Desktop.bat)** para abrir la ventana nativa de escritorio, o en **[`start.bat`](start.bat)** / **[`start.ps1`](start.ps1)** para iniciar el servidor local en `http://127.0.0.1:8000`.
  3. En el primer arranque, [scripts/bootstrap.ps1](scripts/bootstrap.ps1) instala automáticamente `uv`, Python 3.13, dependencias, `FFmpeg`, `FFprobe` y `Deno`.

> **Importante sobre Error 4551 / Windows 11 Smart App Control:** si tu PC tiene activo *Control inteligente de aplicaciones*, Windows puede bloquear archivos `.exe` sin firma digital (*Authenticode*). En ese equipo usa **[`!Download-Desktop.bat`](!Download-Desktop.bat)** (corre sobre Python firmado oficialmente) para abrir exactamente la misma ventana nativa de escritorio.

---

### Linux (`x86_64` / `amd64`)

- **Opción 1 — AppImage universal (`Download-v1.6.0-linux-x86_64.AppImage`) *(soporta auto-actualizaciones)*:**
  ```bash
  chmod +x Download-v1.6.0-linux-x86_64.AppImage
  ./Download-v1.6.0-linux-x86_64.AppImage
  ```
  > Si en Ubuntu 22.04/24.04 aparece un error de FUSE2, instala `sudo apt install libfuse2t64` (o `libfuse2`) o ejecútalo con `./Download-v1.6.0-linux-x86_64.AppImage --appimage-extract-and-run`.
- **Opción 2 — Paquete `.deb` (`Download-v1.6.0-linux-amd64.deb`) *(Debian, Ubuntu, Linux Mint, Pop!_OS)*:**
  ```bash
  sudo apt install ./Download-v1.6.0-linux-amd64.deb
  ```
  Luego ábrelo desde tu menú de aplicaciones o ejecutando `exclaim-download` en terminal.
- **Opción 3 — Portable `.tar.gz` (`Download-Portable-v1.6.0-linux-x86_64.tar.gz`) *(soporta auto-actualizaciones)*:**
  ```bash
  tar -xzf Download-Portable-v1.6.0-linux-x86_64.tar.gz
  ./exclaim-download/exclaim-download
  ```
  Si deseas agregar acceso directo al menú del sistema, ejecuta `./exclaim-download/install-desktop.sh`.
- **Opción 4 — Ejecutar desde código fuente:**
  ```bash
  chmod +x download-desktop.sh start.sh
  ./download-desktop.sh   # Ventana nativa de escritorio (PyQt6-WebEngine)
  ./start.sh              # Servidor web local en http://127.0.0.1:8000 (sin Qt)
  ```
  En la primera ejecución, [scripts/bootstrap.sh](scripts/bootstrap.sh) instala automáticamente `uv`, Python 3.13, dependencias, `FFmpeg`, `FFprobe` y `Deno`.

---

### Android (`.apk` todo incluido)

- **`Download-v1.6.0-android-arm64.apk`**: recomendado para casi todos los teléfonos Android modernos (`arm64-v8a`, más ligero).
- **`Download-v1.6.0-android-universal.apk`**: compatible con cualquier arquitectura (`arm64-v8a`, `armeabi-v7a`, `x86_64`).

**Pasos de instalación:**
1. Descarga el `.apk` desde [Releases](https://github.com/juanpqsi279-lgtm/Download/releases/latest) en tu teléfono.
2. Ábrelo desde Descargas o tu gestor de archivos; si Android lo solicita, activa **Instalar aplicaciones desconocidas** para tu navegador o gestor de archivos.
3. Pulsa **Instalar** y concede permiso de notificaciones/almacenamiento cuando lo pida.
4. Incluye motor `yt-dlp` + `FFmpeg` embebido, guardado directo en `Descargas/!Download/`, **Compartir → `!Download`** desde YouTube/TikTok/Instagram/X y actualización del motor y APK en 1 toque desde Ajustes.

---

### iPhone / iPad (`Download-v1.6.0-ios.ipa` + SideStore / AltStore)

En iOS, los archivos `.ipa` fuera de la App Store deben firmarse con tu Apple ID (con **SideStore** solo necesitas conectar tu iPhone a una PC **una única vez**; después actualizas `!Download` directo en tu iPhone sin PC). Tus descargas se guardan en la app **Archivos → En mi iPhone → `!Download`**.

- **Opción 1 — [SideStore](https://sidestore.io/) *(Recomendado: sin PC para actualizar)*:**
  1. Instala SideStore una sola vez siguiendo **https://sidestore.io/**.
  2. En SideStore entra a **Sources → `+`** y añade la fuente oficial de `!Download`:
     ```
     https://github.com/juanpqsi279-lgtm/Download/releases/latest/download/altstore-source.json
     ```
     *(También puedes copiarla o abrirla directo desde **Ajustes** dentro de `!Download`)*
  3. Instala **`!Download`** y, cada vez que salga una versión nueva, actualízala en **1 toque desde SideStore** sin volver a conectar la PC.

- **Opción 2 — [Sideloadly](https://sideloadly.io/) *(desde PC/Mac)*:**
  1. Descarga Sideloadly (**https://sideloadly.io/**). En Windows usa las versiones **web** de iTunes e iCloud.
  2. Descarga **`Download-v1.6.0-ios.ipa`** desde [Releases](https://github.com/juanpqsi279-lgtm/Download/releases/latest), arrástralo a Sideloadly, escribe tu Apple ID y pulsa **Start**.
  3. En tu iPhone (primera vez): activa *Ajustes → Privacidad y seguridad → Modo de desarrollador* y confía en tu perfil en *Ajustes → General → VPN y gestión de dispositivos*.

- **Opción 3 — [AltStore](https://altstore.io/) / [TrollStore](https://github.com/opa334/TrollStore) / Safari PWA:**
  Compatible con AltServer por Wi-Fi (puedes añadir la misma URL `altstore-source.json`), TrollStore (permanente en iOS compatibles), o usar `!Download` desde **Safari → Compartir → Añadir a pantalla de inicio** ejecutándolo en tu PC/Mac.

---

## Reproductor nativo, Ecualizador y Editor de Metadatos

Además de descargar videos y música, `!Download` incluye un reproductor multimedia integrado disponible en Windows, Linux, Android, iOS y Web:

- **Audio y Video local:** reproduce tus descargas o importa cualquier canción/video externo (`+ Importar archivo`).
- **Ecualizador de 10 bandas + Guía integrada:** incluye `32 Hz – 16 kHz`, Preamp, limitador anti-saturación, **12 presets** (`Graves Potentes`, `Agudos y Claridad`, `Vocal`, `Rock`, `Electrónica`, `Podcast`, etc.) y una **guía práctica de ecualización** con botones de ajuste rápido.
- **Aplicar metadatos (Manual y Automático):** desde **Biblioteca** o **"Aplicar metadatos a externa"**, edita Título, Artista, Álbum, Año, Género, Pista y Carátula, o usa la **Búsqueda automática** para rellenar etiquetas y portada HD en 1 clic directamente dentro del archivo.
- **Listas de reproducción de Audio y Video:** crea listas separadas de solo audio, solo video o mixtas, reordena elementos y reprodúcelas con shuffle, repetición, temporizador, velocidad `0.5x–2.0x` y bucle A-B.

---

## Descarga de playlists completas

`!Download` detecta enlaces de listas de reproducción (**YouTube, YouTube Music, SoundCloud, Bandcamp**, etc.):

- Si pegas un video que incluye `?list=...`, puedes elegir entre analizar **Solo este video** o **Lista completa**.
- En la vista de playlist puedes **marcar o desmarcar** los elementos que quieras descargar y elegir calidad máxima de **video** o formato de **audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).
- En **Windows, Linux, Android e iOS**, los archivos se guardan numerados dentro de una subcarpeta con el nombre de la playlist (`01 - Título`, `02 - Título`...); en modo navegador web se descargan empaquetados en un `.zip`.

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
cp static/index.html static/styles.css static/app.js static/player.js static/icon.png static/manifest.webmanifest ios/App/WebAssets/static/
cd ios && xcodegen generate
```

## Publicar una nueva versión en GitHub Releases

El flujo [release.yml](.github/workflows/release.yml) ejecuta las pruebas, compila los ejecutables y paquetes de **Windows**, **Linux**, **Android** e **iOS**, verifica `--self-check` y publica todos los archivos automáticamente (incluido `altstore-source.json`) al subir una etiqueta `v*`:

```bash
git tag v1.6.0 && git push origin v1.6.0
```

## Licencia

Distribuido bajo licencia **MIT**. Consulta [LICENSE](LICENSE) para más información.
