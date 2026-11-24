@echo off
setlocal disabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No se encontro el entorno virtual .venv. Ejecuta "uv venv --python 3.13 .venv" y reinstala dependencias.
  pause
  exit /b 1
)

echo Iniciando !Download (Juan Corporation) en http://127.0.0.1:8000 ...
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
