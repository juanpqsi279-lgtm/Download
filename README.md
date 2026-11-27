# !Download

Aplicación de escritorio, móvil y web local desarrollada por **Juan Corporation** con estética **iOS 27 Liquid Glass** (modo oscuro y modo claro, animaciones fluidas e inspector completo de metadatos) para descargar contenido multimedia en múltiples calidades de **video** (hasta 4K/8K en MP4, MKV o WebM) o **solo audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).

👉 **[Descargar última versión todo incluido (GitHub Releases)](https://github.com/juanpqsi279-lgtm/Download/releases/latest)**

---

## Guía de instalación por sistema operativo

### Windows (10 / 11)

- **Opción 1 — Instalador (`Download-Setup-v1.5.0.exe`):**
  1. Descarga **`Download-Setup-v1.5.0.exe`** desde [Releases](https://github.com/juanpqsi279-lgtm/Download/releases/latest).
  2. Ejecuta el instalador para crear los accesos directos y activar auto-actualizaciones.
- **Opción 2 — Portable (`Download-Portable-v1.5.0.zip`):**
  1. Descarga y descomprime **`Download-Portable-v1.5.0.zip`**.
  2. Abre **`!Download.exe`**.
- **Opción 3 — Ejecutar desde código fuente (recomendado si Windows bloquea el `.exe`):**
  1. Clona o descarga este repositorio.
  2. Haz doble clic en **[`!Download-Desktop.bat`](!Download-Desktop.bat)** para abrir la ventana nativa de escritorio, o en **[`start.bat`](start.bat)** / **[`start.ps1`](start.ps1)** para iniciar el servidor local en `http://127.0.0.1:8000`.
  3. En el primer arranque, [scripts/bootstrap.ps1](scripts/bootstrap.ps1) instala automáticamente `uv`, Python 3.13, dependencias, `FFmpeg`, `FFprobe` y `Deno`.

> **Importante sobre Error 4551 / Windows 11 Smart App Control:** si tu PC tiene activo *Control inteligente de aplicaciones*, Windows puede bloquear archivos `.exe` sin firma digital (*Authenticode*). En ese equipo usa **[`!Download-Desktop.bat`](!Download-Desktop.bat)** (corre sobre Python firmado oficialmente) para abrir exactamente la misma ventana nativa de escritorio.

---

### Linux (`x86_64` / `amd64`)

- **Opción 1 — AppImage universal (`Download-v1.5.0-linux-x86_64.AppImage`) *(soporta auto-actualizaciones)*:**
  ```bash
  chmod +x Download-v1.5.0-linux-x86_64.AppImage
  ./Download-v1.5.0-linux-x86_64.AppImage
  ```
  > Si en Ubuntu 22.04/24.04 aparece un error de FUSE2, instala `sudo apt install libfuse2t64` (o `libfuse2`) o ejecútalo con `./Download-v1.5.0-linux-x86_64.AppImage --appimage-extract-and-run`.
- **Opción 2 — Paquete `.deb` (`Download-v1.5.0-linux-amd64.deb`) *(Debian, Ubuntu, Linux Mint, Pop!_OS)*:**
  ```bash
  sudo apt install ./Download-v1.5.0-linux-amd64.deb
  ```
  Luego ábrelo desde tu menú de aplicaciones o ejecutando `exclaim-download` en terminal.
- **Opción 3 — Portable `.tar.gz` (`Download-Portable-v1.5.0-linux-x86_64.tar.gz`) *(soporta auto-actualizaciones)*:**
  ```bash
  tar -xzf Download-Portable-v1.5.0-linux-x86_64.tar.gz
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

- **`Download-v1.5.0-android-arm64.apk`**: recomendado para casi todos los teléfonos Android modernos (`arm64-v8a`, más ligero).
- **`Download-v1.5.0-android-universal.apk`**: compatible con cualquier arquitectura (`arm64-v8a`, `armeabi-v7a`, `x86_64`).

**Pasos de instalación:**
1. Descarga el `.apk` desde [Releases](https://github.com/juanpqsi279-lgtm/Download/releases/latest) en tu teléfono.
2. Ábrelo desde Descargas o tu gestor de archivos; si Android lo solicita, activa **Instalar aplicaciones desconocidas** para tu navegador o gestor de archivos.
3. Pulsa **Instalar** y concede permiso de notificaciones/almacenamiento cuando lo pida.
4. Incluye motor `yt-dlp` + `FFmpeg` embebido, guardado directo en `Descargas/!Download/`, **Compartir → `!Download`** desde YouTube/TikTok/Instagram/X y actualización del motor y APK desde Ajustes.

---

### iPhone / iPad (`Download-v1.5.0-ios.ipa` + Safari PWA)

En iOS, los archivos `.ipa` fuera de la App Store deben firmarse con tu Apple ID (la primera vez requiere conectar tu iPhone a una PC o Mac). Tus descargas se guardan en la app **Archivos → En mi iPhone → `!Download`** (con botón para compartir o guardar en Fotos).

- **Opción 1 — [Sideloadly](https://sideloadly.io/) *(la más rápida desde PC/Mac)*:**
  1. Descarga e instala Sideloadly desde su sitio oficial: **https://sideloadly.io/**.
  2. **Solo en Windows:** instala las versiones **web** (NO las de Microsoft Store) de **[iTunes 64-bit](https://www.apple.com/itunes/win64)** ([32-bit](https://www.apple.com/itunes/win32)) e **[iCloud para Windows](https://support.apple.com/HT204283)** (también enlazados dentro de [sideloadly.io](https://sideloadly.io/)). Reinicia la PC si es la primera vez.
  3. Descarga **`Download-v1.5.0-ios.ipa`** desde [Releases](https://github.com/juanpqsi279-lgtm/Download/releases/latest).
  4. Conecta tu iPhone por cable USB de datos, desbloquéalo y pulsa **Confiar** si te lo pregunta.
  5. Arrastra el `.ipa` a Sideloadly, escribe tu Apple ID y pulsa **Start**.
  6. En tu iPhone (solo la primera vez):
     - En **iOS 16+**, activa *Ajustes → Privacidad y seguridad → Modo de desarrollador*.
     - Ve a *Ajustes → General → VPN y gestión de dispositivos* y pulsa **Confiar** en tu Apple ID.
  > Con Apple ID gratuito la firma caduca cada 7 días; Sideloadly puede renovarla automáticamente por Wi-Fi mientras tu PC esté encendida.

- **Opción 2 — [SideStore](https://sidestore.io/) *(PC solo 1 vez; luego instalas y renuevas desde el mismo iPhone)*:**
  Instala SideStore una vez siguiendo la guía oficial en **https://sidestore.io/**; después podrás abrir `Download-v1.5.0-ios.ipa` y renovarlo directo en tu iPhone sin PC.

- **Opción 3 — [AltStore](https://altstore.io/) *(PC/Mac + iPhone por Wi-Fi)*:**
  Instala AltServer en tu PC/Mac desde **https://altstore.io/** e instala el `.ipa` desde AltStore en tu iPhone.

- **Opción 4 — [TrollStore](https://github.com/opa334/TrollStore) *(solo versiones de iOS compatibles, sin caducidad de 7 días)*:**
  Permite instalar `Download-v1.5.0-ios.ipa` de forma permanente desde **https://github.com/opa334/TrollStore**.

- **Opción 5 — Sin instalar `.ipa` (PWA en Safari):**
  Ejecuta `!Download` en tu PC o Mac dentro de la misma red Wi-Fi, abre la dirección en **Safari** desde tu iPhone y pulsa **Compartir → Añadir a pantalla de inicio**.

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
cp static/index.html static/styles.css static/app.js static/icon.png static/manifest.webmanifest ios/App/WebAssets/static/
cd ios && xcodegen generate
```

## Publicar una nueva versión en GitHub Releases

El flujo [release.yml](.github/workflows/release.yml) ejecuta las pruebas, compila los ejecutables y paquetes de **Windows**, **Linux**, **Android** e **iOS**, verifica `--self-check` y publica todos los archivos automáticamente al subir una etiqueta `v*`:

```bash
git tag v1.5.0 && git push origin v1.5.0
```

## Licencia

Distribuido bajo licencia **MIT**. Consulta [LICENSE](LICENSE) para más información.
