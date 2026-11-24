@echo off
setlocal disabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo No se encontro .venv\Scripts\pythonw.exe. Reinstala el entorno virtual con uv.
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" desktop_main.py
