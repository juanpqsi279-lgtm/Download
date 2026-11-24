@echo off
setlocal disabledelayedexpansion
cd /d "%~dp0"

set "NEED_SETUP=0"
if not exist ".venv\Scripts\python.exe" set "NEED_SETUP=1"
if not exist "bin\ffmpeg.exe" set "NEED_SETUP=1"
if not exist "bin\ffprobe.exe" set "NEED_SETUP=1"
if not exist "bin\deno.exe" set "NEED_SETUP=1"

if "%NEED_SETUP%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
  if errorlevel 1 (
    echo.
    echo No se pudo completar la configuracion inicial de !Download.
    pause
    exit /b 1
  )
)

echo Iniciando !Download (Juan Corporation) en http://127.0.0.1:8000 ...
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
