# !Download

Aplicación de escritorio y web local desarrollada por **Juan Corporation** con estética **iOS 27 Liquid Glass** (modo oscuro y modo claro, animaciones fluidas e inspector completo de metadatos) para descargar contenido multimedia en múltiples calidades de **video** (hasta 4K/8K en MP4, MKV o WebM) o **solo audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).

## Ejecución como aplicación de escritorio (Windows)

- **Lanzador nativo directo (sin navegador ni consola negra):** haz doble clic en `!Download-Desktop.bat`, o ejecuta:
  ```powershell
  .\.venv\Scripts\pythonw.exe desktop_main.py
  ```
- **Ejecutable empaquetado (todo incluido):** compilado en `dist\!Download\!Download.exe` (incluye `FFmpeg`, `FFprobe`, `Deno` y `yt-dlp`).
  > **Nota sobre Windows 11 Smart App Control:** en equipos con Control de aplicaciones / Smart App Control activo, Windows bloquea ejecutables locales sin firma digital (*Authenticode*). En ese caso, usa `!Download-Desktop.bat` para abrir la misma ventana nativa en este equipo, o firma el `.exe` antes de distribuirlo.

## Ejecución en modo web local

Haz doble clic en `start.bat` o ejecuta en PowerShell:

```powershell
.\start.ps1
```

## Sistema de actualizaciones en 2 niveles

1. **Actualización del motor (`yt-dlp`):** dentro de **Ajustes** en `!Download`, pulsa **Actualizar motor** para descargar el paquete zipapp oficial más reciente de `yt-dlp` sin recompilar la aplicación.
2. **Actualizaciones de `!Download`:** al abrir la app, consulta `https://api.github.com/repos/juanpqsi279-lgtm/Download/releases/latest` y permite descargar e instalar nuevas versiones publicadas en GitHub Releases.

## Cómo compilar el ejecutable desde cero

```powershell
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.\.venv\Scripts\python.exe scripts\generate_icon.py
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean build.spec
```

## Publicar repositorio y primera versión (`v1.0.0`) en GitHub

Crea el repositorio vacío `Download` en tu cuenta de GitHub (`https://github.com/juanpqsi279-lgtm/Download`) o inicia sesión con GitHub CLI (`gh auth login`), y luego ejecuta:

```bash
git remote add origin https://github.com/juanpqsi279-lgtm/Download.git
git push -u origin main
git tag v1.0.0 && git push origin v1.0.0
```

Al subir la etiqueta `v1.0.0`, el flujo [release.yml](.github/workflows/release.yml) compilará automáticamente el ejecutable, verificará `--self-check`, generará el instalador y el `.zip` portable y los publicará en **GitHub Releases**.
