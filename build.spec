# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

hiddenimports = [
    "webview",
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
if IS_WINDOWS:
    hiddenimports += [
        "clr",
        "clr_loader",
        "pythonnet",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
    ]
elif IS_LINUX:
    hiddenimports += [
        "webview.platforms.qt",
        "qtpy",
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtNetwork",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.sip",
    ]

hiddenimports += collect_submodules("yt_dlp")
hiddenimports += collect_submodules("yt_dlp_ejs")

datas = [(str(ROOT / "static"), "static")]
binaries = []

if IS_WINDOWS:
    for tool_name in ("ffmpeg.exe", "ffprobe.exe", "deno.exe"):
        tool_path = ROOT / "bin" / tool_name
        if tool_path.is_file():
            binaries.append((str(tool_path), "bin"))
else:
    for tool_name in ("ffmpeg", "ffprobe", "deno"):
        tool_path = ROOT / "bin" / tool_name
        if tool_path.is_file():
            # Bundle standalone Linux binaries as datas so PyInstaller skips ELF RPATH mangling.
            datas.append((str(tool_path), "bin"))

wv_datas, wv_bins, wv_hidden = collect_all("webview")
datas += wv_datas
binaries += wv_bins
hiddenimports += wv_hidden

yt_ejs_datas, yt_ejs_bins, yt_ejs_hidden = collect_all("yt_dlp_ejs")
datas += yt_ejs_datas
binaries += yt_ejs_bins
hiddenimports += yt_ejs_hidden

if IS_LINUX:
    qtpy_datas, qtpy_bins, qtpy_hidden = collect_all("qtpy")
    datas += qtpy_datas
    binaries += qtpy_bins
    hiddenimports += qtpy_hidden

excludes = ["tkinter", "matplotlib", "numpy", "scipy", "pandas"]
if IS_WINDOWS:
    excludes += ["PyQt6", "PySide6", "qtpy", "gi"]
elif IS_LINUX:
    excludes += ["clr", "clr_loader", "pythonnet"]

a = Analysis(
    ["desktop_main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(dict.fromkeys(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe_kwargs = {
    "exclude_binaries": True,
    "name": "exclaim-download" if IS_LINUX else "!Download",
    "debug": False,
    "bootloader_ignore_signals": False,
    "strip": False,
    "upx": False,
    "console": IS_LINUX,
    "disable_windowed_traceback": False,
    "argv_emulation": False,
    "target_arch": None,
    "codesign_identity": None,
    "entitlements_file": None,
}
if IS_WINDOWS:
    exe_kwargs["icon"] = str(ROOT / "static" / "icon.ico")
    exe_kwargs["version"] = str(ROOT / "version_info.txt")

exe = EXE(pyz, a.scripts, [], **exe_kwargs)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="exclaim-download" if IS_LINUX else "!Download",
)
