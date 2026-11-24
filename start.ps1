$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$ffmpegExe = Join-Path $PSScriptRoot "bin\ffmpeg.exe"
$ffprobeExe = Join-Path $PSScriptRoot "bin\ffprobe.exe"
$denoExe = Join-Path $PSScriptRoot "bin\deno.exe"

if (
    (-not (Test-Path $pythonExe)) -or
    (-not (Test-Path $ffmpegExe)) -or
    (-not (Test-Path $ffprobeExe)) -or
    (-not (Test-Path $denoExe))
) {
    & (Join-Path $PSScriptRoot "scripts\bootstrap.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo completar la configuración inicial de !Download."
    }
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
