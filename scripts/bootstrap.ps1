$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $root ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$venvPyw = Join-Path $venvDir "Scripts\pythonw.exe"
$binDir = Join-Path $root "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"
$denoExe = Join-Path $binDir "deno.exe"

if (
    (Test-Path $venvPy) -and
    (Test-Path $venvPyw) -and
    (Test-Path $ffmpegExe) -and
    (Test-Path $ffprobeExe) -and
    (Test-Path $denoExe)
) {
    Write-Host "Entorno de !Download listo." -ForegroundColor Green
    exit 0
}

function Resolve-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $localUv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $localUv) { return $localUv }
    $cargoUv = Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"
    if (Test-Path $cargoUv) { return $cargoUv }
    return $null
}

function Download-Archive {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$DestPath
    )
    $curlCmd = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curlCmd) {
        & $curlCmd.Source -fSL --retry 3 $Url -o $DestPath
        if ($LASTEXITCODE -eq 0 -and (Test-Path $DestPath)) {
            return
        }
    }
    Invoke-WebRequest -Uri $Url -OutFile $DestPath -UseBasicParsing
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Configurando !Download por primera vez (Juan Corporation)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $root

if (-not (Test-Path $venvPy) -or -not (Test-Path $venvPyw)) {
    $uvExe = Resolve-Uv
    if (-not $uvExe) {
        Write-Host "[1/3] Instalando uv (gestor de Python)..." -ForegroundColor Yellow
        Invoke-Expression ((Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing).Content)
        $uvExe = Resolve-Uv
        if (-not $uvExe) {
            throw "No se pudo encontrar uv después de instalarlo."
        }
    }

    Write-Host "[1/3] Creando entorno Python 3.13..." -ForegroundColor Yellow
    & $uvExe venv --python 3.13 $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Falló la creación del entorno virtual con uv." }

    Write-Host "[2/3] Instalando dependencias de !Download..." -ForegroundColor Yellow
    & $uvExe pip install --python $venvPy $root
    if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias." }
}

$needFfmpeg = (-not (Test-Path $ffmpegExe)) -or (-not (Test-Path $ffprobeExe))
$needDeno = -not (Test-Path $denoExe)

if ($needFfmpeg -or $needDeno) {
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    $tmpDir = Join-Path $env:TEMP ("exclaim-dl-setup-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

    try {
        if ($needFfmpeg) {
            Write-Host "[3/3] Descargando FFmpeg y FFprobe portables..." -ForegroundColor Yellow
            $ffmpegZip = Join-Path $tmpDir "ffmpeg.zip"
            Download-Archive -Url "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip" -DestPath $ffmpegZip
            $ffmpegExtract = Join-Path $tmpDir "ffmpeg"
            Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force
            $foundFfmpeg = Get-ChildItem -Path $ffmpegExtract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
            $foundFfprobe = Get-ChildItem -Path $ffmpegExtract -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
            if (-not $foundFfmpeg -or -not $foundFfprobe) {
                throw "No se encontraron ffmpeg.exe o ffprobe.exe dentro del archivo descargado."
            }
            Copy-Item -Path $foundFfmpeg.FullName -Destination $ffmpegExe -Force
            Copy-Item -Path $foundFfprobe.FullName -Destination $ffprobeExe -Force
        }

        if ($needDeno) {
            Write-Host "[3/3] Descargando Deno portable..." -ForegroundColor Yellow
            $denoZip = Join-Path $tmpDir "deno.zip"
            Download-Archive -Url "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" -DestPath $denoZip
            $denoExtract = Join-Path $tmpDir "deno"
            Expand-Archive -Path $denoZip -DestinationPath $denoExtract -Force
            $foundDeno = Get-ChildItem -Path $denoExtract -Recurse -Filter "deno.exe" | Select-Object -First 1
            if (-not $foundDeno) {
                throw "No se encontró deno.exe dentro del archivo descargado."
            }
            Copy-Item -Path $foundDeno.FullName -Destination $denoExe -Force
        }
    } finally {
        Remove-Item -Path $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "!Download quedó configurado correctamente." -ForegroundColor Green
exit 0
