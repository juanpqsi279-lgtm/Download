# !Download

Aplicación de escritorio y web local desarrollada por **Juan Corporation** con estética **iOS 27 Liquid Glass** (modo oscuro y modo claro, animaciones fluidas e inspector completo de metadatos) para descargar contenido multimedia en múltiples calidades de **video** (hasta 4K/8K en MP4, MKV o WebM) o **solo audio** (`MP3`, `M4A`, `Opus`, `FLAC`, `WAV`).

## Descargar para Windows (Recomendado)

Si solo quieres usar `!Download` sin instalar herramientas ni compilar nada, descarga la última versión todo incluido desde **GitHub Releases**:

👉 **[Descargar última versión (Releases)](https://github.com/juanpqsi279-lgtm/Download/releases/latest)**

- **`Download-Setup-v1.0.0.exe`**: instalador clásico para Windows (crea accesos directos y soporta auto-actualizaciones).
- **`Download-Portable-v1.0.0.zip`**: versión portable (descomprimir y abrir `!Download.exe`).

---

## Ejecutar desde el código fuente (todo automático)

Si descargaste o clonaste el repositorio directamente, simplemente haz doble clic en:

- **[`!Download-Desktop.bat`](!Download-Desktop.bat)** — abre `!Download` en su propia ventana nativa de escritorio (sin abrir navegador).
- **[`start.bat`](start.bat)** o **[`start.ps1`](start.ps1)** — inicia el servidor local en `http://127.0.0.1:8000`.

> En la primera ejecución, [scripts/bootstrap.ps1](scripts/bootstrap.ps1) detecta automáticamente si falta `.venv` o `bin/` e instala `uv`, Python 3.13, dependencias, `FFmpeg`, `FFprobe` y `Deno` de forma automática.

> **Nota sobre Windows 11 Smart App Control:** en equipos con Control de aplicaciones / Smart App Control activo, Windows puede bloquear ejecutables `.exe` sin firma digital (*Authenticode*). En ese caso, usa `!Download-Desktop.bat` para abrir exactamente la misma ventana nativa.

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

## Publicar una nueva versión en GitHub Releases

El flujo [release.yml](.github/workflows/release.yml) ejecuta las pruebas, compila el ejecutable, verifica `--self-check`, genera el instalador y el `.zip` portable y publica los archivos automáticamente al subir una etiqueta `v*`:

```bash
git tag v1.0.1 && git push origin v1.0.1
```
