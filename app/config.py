"""Configuration, settings persistence, and runtime binary discovery for !Download."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

APP_NAME = "!Download"
APP_DEVELOPER = "Juan Corporation"
APP_VERSION = "1.5.0"
GITHUB_REPO = os.getenv("DOWNLOAD_GITHUB_REPO", "juanpqsi279-lgtm/Download")

IS_FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else PROJECT_ROOT

IS_APPIMAGE = bool(os.getenv("APPIMAGE"))
APPIMAGE_PATH: Path | None = (
    Path(os.environ["APPIMAGE"]).resolve() if os.getenv("APPIMAGE") else None
)

STATIC_DIR = BUNDLE_DIR / "static"
BIN_DIR = APP_DIR / "bin"


def _resolve_user_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA") or Path.home()) / APP_DEVELOPER / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DEVELOPER / APP_NAME
    xdg_data = os.getenv("XDG_DATA_HOME")
    base = Path(xdg_data) if xdg_data else (Path.home() / ".local" / "share")
    return base / "exclaim-download"


USER_DATA_DIR = _resolve_user_data_dir()
UPDATES_DIR = USER_DATA_DIR / "updates"
SETTINGS_FILE = USER_DATA_DIR / "settings.json"
DOWNLOADS_DIR = (USER_DATA_DIR / "temp_downloads") if IS_FROZEN else (PROJECT_ROOT / "downloads")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
MAX_CONCURRENT_DOWNLOADS = max(1, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3")))
FILE_TTL_SECONDS = max(60, int(os.getenv("FILE_TTL_SECONDS", "1800")))
COOKIES_FILE = os.getenv("COOKIES_FILE", str(APP_DIR / "cookies.txt"))


def is_desktop_mode() -> bool:
    """Return True when running inside the native desktop window or frozen binary."""
    return os.getenv("DOWNLOAD_DESKTOP", "0") == "1" or IS_FROZEN


def resolve_cookies_file() -> Path | None:
    """Locate cookies.txt from COOKIES_FILE / APP_DIR first, then USER_DATA_DIR."""
    for candidate in (Path(COOKIES_FILE), USER_DATA_DIR / "cookies.txt"):
        if candidate.is_file():
            return candidate
    return None


def can_self_update() -> bool:
    """Return True if the current runtime supports in-place self-updates."""
    if sys.platform == "win32":
        return IS_FROZEN
    if sys.platform.startswith("linux"):
        appimage = os.getenv("APPIMAGE")
        if appimage:
            return os.access(Path(appimage).resolve().parent, os.W_OK)
        if IS_FROZEN:
            return os.access(APP_DIR, os.W_OK)
        return False
    return False


def _candidate_bin_dirs() -> list[Path]:
    dirs = [APP_DIR / "bin", BUNDLE_DIR / "bin", USER_DATA_DIR / "bin"]
    unique: list[Path] = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def ensure_runtime_paths() -> None:
    """Create runtime directories and prepend bundled bin/ directories to PATH."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)

    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    for bin_dir in reversed(_candidate_bin_dirs()):
        if bin_dir.is_dir():
            bin_str = str(bin_dir)
            if bin_str not in path_parts:
                path_parts.insert(0, bin_str)
    os.environ["PATH"] = os.pathsep.join(path_parts)


def resolve_binary(name: str) -> str | None:
    """Locate a binary across app bin/ directories first, then system PATH."""
    for bin_dir in _candidate_bin_dirs():
        if sys.platform == "win32":
            candidates = (bin_dir / f"{name}.exe", bin_dir / name)
            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)
        else:
            candidate = bin_dir / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return shutil.which(name)


def _xdg_user_download_dir(home: Path | None = None) -> Path | None:
    """Parse XDG_DOWNLOAD_DIR from ~/.config/user-dirs.dirs if present and valid."""
    base_home = home or Path.home()
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    config_dir = Path(xdg_config) if xdg_config else (base_home / ".config")
    user_dirs = config_dir / "user-dirs.dirs"
    if not user_dirs.is_file():
        return None
    try:
        content = user_dirs.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^XDG_DOWNLOAD_DIR\s*=\s*(.+)$', line)
        if not match:
            continue
        raw_val = match.group(1).strip().strip('"').strip("'")
        expanded = raw_val.replace("${HOME}", str(base_home)).replace("$HOME", str(base_home))
        candidate = Path(expanded).expanduser()
        if candidate.is_dir():
            return candidate
    return None


def default_download_dir() -> Path:
    """Default folder where completed downloads are saved in desktop mode."""
    home = Path.home()
    if sys.platform != "win32":
        xdg_downloads = _xdg_user_download_dir(home)
        if xdg_downloads is not None:
            return xdg_downloads

    for folder_name in ("Downloads", "Descargas"):
        candidate = home / folder_name
        if candidate.exists():
            return candidate
    return home


def load_settings() -> dict[str, Any]:
    """Load persisted user preferences (theme and download directory)."""
    defaults: dict[str, Any] = {
        "theme": "dark",
        "download_dir": str(default_download_dir()),
    }
    if not SETTINGS_FILE.is_file():
        return defaults
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            if raw.get("theme") in {"dark", "light", "system"}:
                defaults["theme"] = raw["theme"]
            if isinstance(raw.get("download_dir"), str) and raw["download_dir"].strip():
                defaults["download_dir"] = raw["download_dir"].strip()
    except Exception:
        pass
    return defaults


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    """Persist updated user settings safely."""
    current = load_settings()
    for key, value in patch.items():
        if value is not None:
            current[key] = value
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def get_download_dir() -> Path:
    """Return active desktop download destination directory, ensuring it exists."""
    configured = Path(load_settings().get("download_dir") or default_download_dir())
    try:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    except Exception:
        fallback = default_download_dir()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


@lru_cache(maxsize=8)
def _read_binary_version(binary_path: str, flag: str) -> str | None:
    """Run a binary with a version flag and return its first output line."""
    try:
        run_kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": 5,
            "check": False,
        }
        if sys.platform == "win32":
            run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run([binary_path, flag], **run_kwargs)
        output = (completed.stdout or completed.stderr or "").strip()
        if not output:
            return None
        return output.splitlines()[0].strip()
    except Exception:
        return None


def get_runtime_status() -> dict[str, dict[str, str | bool | None]]:
    """Return availability and versions for yt-dlp, FFmpeg, FFprobe, and Deno."""
    ensure_runtime_paths()

    yt_dlp_version: str | None = None
    yt_dlp_path: str | None = None
    using_override = False
    try:
        import yt_dlp
        import yt_dlp.version

        yt_dlp_version = yt_dlp.version.__version__
        yt_dlp_path = getattr(yt_dlp, "__file__", None)
        override_zip = UPDATES_DIR / "yt-dlp.zip"
        if yt_dlp_path and str(override_zip) in yt_dlp_path:
            using_override = True
    except Exception:
        yt_dlp_version = None

    ffmpeg_path = resolve_binary("ffmpeg")
    ffprobe_path = resolve_binary("ffprobe")
    deno_path = resolve_binary("deno")

    return {
        "yt_dlp": {
            "available": yt_dlp_version is not None,
            "version": yt_dlp_version,
            "path": yt_dlp_path,
            "using_override": using_override,
        },
        "ffmpeg": {
            "available": ffmpeg_path is not None,
            "version": _read_binary_version(ffmpeg_path, "-version") if ffmpeg_path else None,
            "path": ffmpeg_path,
        },
        "ffprobe": {
            "available": ffprobe_path is not None,
            "version": _read_binary_version(ffprobe_path, "-version") if ffprobe_path else None,
            "path": ffprobe_path,
        },
        "deno": {
            "available": deno_path is not None,
            "version": _read_binary_version(deno_path, "--version") if deno_path else None,
            "path": deno_path,
        },
    }
