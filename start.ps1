$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Error "No se encontró .venv\Scripts\python.exe. Crea el entorno virtual primero."
    exit 1
}

$hostAddr = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$portNum = if ($env:PORT) { $env:PORT } else { "8000" }
$url = "http://${hostAddr}:${portNum}"

Write-Host "Iniciando !Download (Juan Corporation) en $url ..." -ForegroundColor Cyan
Start-Job -ScriptBlock {
    param($targetUrl)
    Start-Sleep -Seconds 2
    Start-Process $targetUrl
} -ArgumentList $url | Out-Null

& $pythonExe -m uvicorn app.main:app --host $hostAddr --port $portNum
