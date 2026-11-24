# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

hiddenimports = [
    "clr",
    "clr_loader",
    "pythonnet",
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "httpx",
    "mutagen",
    "yt_dlp",
    "yt_dlp_ejs",
]
hiddenimports += collect_submodules("yt_dlp")
hiddenimports += collect_submodules("yt_dlp_ejs")

datas = [(str(ROOT / "static"), "static")]
binaries = []

for tool_name in ("ffmpeg.exe", "ffprobe.exe", "deno.exe"):
    tool_path = ROOT / "bin" / tool_name
    if tool_path.is_file():
        binaries.append((str(tool_path), "bin"))

wv_datas, wv_bins, wv_hidden = collect_all("webview")
datas += wv_datas
binaries += wv_bins
hiddenimports += wv_hidden

yt_ejs_datas, yt_ejs_bins, yt_ejs_hidden = collect_all("yt_dlp_ejs")
datas += yt_ejs_datas
binaries += yt_ejs_bins
hiddenimports += yt_ejs_hidden

a = Analysis(
    ["desktop_main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(dict.fromkeys(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="!Download",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "static" / "icon.ico"),
    version=str(ROOT / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="!Download",
)
