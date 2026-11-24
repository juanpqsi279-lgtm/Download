@echo off
setlocal disabledelayedexpansion
cd /d "%~dp0"

set "NEED_SETUP=0"
if not exist ".venv\Scripts\pythonw.exe" set "NEED_SETUP=1"
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

start "" ".venv\Scripts\pythonw.exe" desktop_main.py
