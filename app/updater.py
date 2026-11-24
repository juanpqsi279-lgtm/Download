"""Two-level updater for !Download: yt-dlp zipapp override and GitHub Releases app updates."""

from __future__ import annotations

import importlib.abc
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
import zipimport
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import APP_DIR, APP_VERSION, GITHUB_REPO, IS_FROZEN, UPDATES_DIR

ALLOWED_GITHUB_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}

YTDLP_OVERRIDE_ZIP = UPDATES_DIR / "yt-dlp.zip"
YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_ZIPAPP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"


class ZipOverrideFinder(importlib.abc.MetaPathFinder):
    """Load specified top-level packages from an updated zipapp ahead of frozen modules."""

    def __init__(self, zip_path: Path, prefixes: tuple[str, ...] = ("yt_dlp", "yt_dlp_ejs")) -> None:
        self.zip_path = Path(zip_path)
        self.prefixes = prefixes
        self._importer = zipimport.zipimporter(str(self.zip_path))

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        root = fullname.split(".", 1)[0]
        if root not in self.prefixes:
            return None
        try:
            return self._importer.find_spec(fullname, target)
        except Exception:
            return None


def _is_valid_ytdlp_zip(zip_path: Path) -> bool:
    if not zip_path.is_file():
        return False
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            return "yt_dlp/__init__.py" in names and "yt_dlp/version.py" in names
    except Exception:
        return False


def install_ytdlp_override(zip_path: Path = YTDLP_OVERRIDE_ZIP) -> bool:
    """Prepend ZipOverrideFinder to sys.meta_path if a valid yt-dlp zipapp override exists."""
    if not _is_valid_ytdlp_zip(zip_path):
        return False

    for finder in sys.meta_path:
        if isinstance(finder, ZipOverrideFinder) and finder.zip_path.resolve() == zip_path.resolve():
            return True

    sys.meta_path.insert(0, ZipOverrideFinder(zip_path))
    return True


def parse_semver(tag: str | None) -> tuple[int, ...]:
    """Parse version strings like 'v1.2.3' or '2026.11.23' into comparable integer tuples."""
    if not tag:
        return (0,)
    nums = [int(part) for part in re.findall(r"\d+", tag)]
    return tuple(nums) if nums else (0,)


def _compare_versions(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    max_len = max(len(a), len(b))
    pa = a + (0,) * (max_len - len(a))
    pb = b + (0,) * (max_len - len(b))
    if pa > pb:
        return 1
    if pa < pb:
        return -1
    return 0


def update_ytdlp_engine() -> dict[str, Any]:
    """Check GitHub for the latest yt-dlp release and install its zipapp override."""
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)

    current_version = "desconocida"
    try:
        import yt_dlp.version

        current_version = yt_dlp.version.__version__
    except Exception:
        pass

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "!Download-Updater/1.0"}
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(YTDLP_RELEASE_API, headers=headers)
            resp.raise_for_status()
            release = resp.json()
    except httpx.HTTPError as exc:
        return {
            "updated": False,
            "current_version": current_version,
            "latest_version": None,
            "restart_required": False,
            "message": f"No se pudo consultar la última versión de yt-dlp: {exc}",
        }

    latest_tag = str(release.get("tag_name") or "").lstrip("v")
    if not latest_tag:
        return {
            "updated": False,
            "current_version": current_version,
            "latest_version": None,
            "restart_required": False,
            "message": "GitHub no devolvió una versión válida para yt-dlp.",
        }

    if _compare_versions(parse_semver(latest_tag), parse_semver(current_version)) <= 0:
        return {
            "updated": False,
            "current_version": current_version,
            "latest_version": latest_tag,
            "restart_required": False,
            "message": f"El motor yt-dlp ya está al día (v{current_version}).",
        }

    assets = release.get("assets") or []
    zipapp_url = YTDLP_ZIPAPP_URL
    for asset in assets:
        if asset.get("name") == "yt-dlp" and asset.get("browser_download_url"):
            zipapp_url = asset["browser_download_url"]
            break

    tmp_zip = UPDATES_DIR / "yt-dlp.zip.tmp"
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            with client.stream("GET", zipapp_url, headers=headers) as stream:
                stream.raise_for_status()
                with tmp_zip.open("wb") as handle:
                    for chunk in stream.iter_bytes():
                        handle.write(chunk)

        if not _is_valid_ytdlp_zip(tmp_zip):
            tmp_zip.unlink(missing_ok=True)
            return {
                "updated": False,
                "current_version": current_version,
                "latest_version": latest_tag,
                "restart_required": False,
                "message": "El paquete descargado de yt-dlp no es válido.",
            }

        os.replace(tmp_zip, YTDLP_OVERRIDE_ZIP)
    except Exception as exc:
        tmp_zip.unlink(missing_ok=True)
        return {
            "updated": False,
            "current_version": current_version,
            "latest_version": latest_tag,
            "restart_required": False,
            "message": f"Error al descargar la actualización de yt-dlp: {exc}",
        }

    return {
        "updated": True,
        "current_version": current_version,
        "latest_version": latest_tag,
        "restart_required": True,
        "message": f"Motor actualizado a yt-dlp {latest_tag}. Reinicia la app para activarlo.",
    }


def _pick_windows_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    setup_exe = next(
        (
            a
            for a in assets
            if str(a.get("name") or "").lower().endswith(".exe")
            and "setup" in str(a.get("name") or "").lower()
        ),
        None,
    )
    if setup_exe:
        return setup_exe

    any_exe = next(
        (a for a in assets if str(a.get("name") or "").lower().endswith(".exe")),
        None,
    )
    if any_exe:
        return any_exe

    return next(
        (a for a in assets if str(a.get("name") or "").lower().endswith(".zip")),
        None,
    )


def check_app_update(repo: str = GITHUB_REPO, current_version: str = APP_VERSION) -> dict[str, Any]:
    """Check GitHub Releases for a newer version of !Download."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "!Download-Updater/1.0"}

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(api_url, headers=headers)
            if resp.status_code == 404:
                return {
                    "update_available": False,
                    "current_version": current_version,
                    "latest_version": None,
                    "release_notes": None,
                    "release_url": f"https://github.com/{repo}/releases",
                    "asset_name": None,
                    "asset_url": None,
                    "asset_size": None,
                    "message": "Aún no hay lanzamientos publicados en GitHub para este repositorio.",
                }
            resp.raise_for_status()
            release = resp.json()
    except httpx.HTTPError as exc:
        return {
            "update_available": False,
            "current_version": current_version,
            "latest_version": None,
            "release_notes": None,
            "release_url": f"https://github.com/{repo}/releases",
            "asset_name": None,
            "asset_url": None,
            "asset_size": None,
            "message": f"No se pudo conectar con GitHub Releases: {exc}",
        }

    latest_tag = str(release.get("tag_name") or "").lstrip("v")
    is_newer = _compare_versions(parse_semver(latest_tag), parse_semver(current_version)) > 0
    asset = _pick_windows_asset(release.get("assets") or [])

    return {
        "update_available": bool(is_newer),
        "current_version": current_version,
        "latest_version": latest_tag or None,
        "release_notes": release.get("body") or None,
        "release_url": release.get("html_url") or f"https://github.com/{repo}/releases",
        "asset_name": asset.get("name") if asset else None,
        "asset_url": asset.get("browser_download_url") if asset else None,
        "asset_size": asset.get("size") if asset else None,
        "message": (
            f"¡Nueva versión v{latest_tag} disponible!"
            if is_newer
            else f"Tienes la versión más reciente (v{current_version})."
        ),
    }


def _validate_github_asset_url(asset_url: str) -> str:
    parsed = urlparse((asset_url or "").strip())
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in ALLOWED_GITHUB_DOWNLOAD_HOSTS:
        raise ValueError("La URL de actualización debe provenir de GitHub Releases.")
    return parsed.geturl()


def download_and_apply_app_update(asset_url: str, asset_name: str) -> dict[str, Any]:
    """Download an official release asset from GitHub and apply it cleanly."""
    if not IS_FROZEN:
        raise ValueError("La auto-actualización automática solo funciona desde el ejecutable instalado (.exe).")

    safe_url = _validate_github_asset_url(asset_url)
    safe_name = Path(asset_name or "update.bin").name
    if not safe_name.lower().endswith((".exe", ".zip")):
        raise ValueError("El archivo de actualización debe ser un instalador .exe o paquete .zip.")

    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPDATES_DIR / safe_name
    headers = {"User-Agent": "!Download-Updater/1.0"}

    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        with client.stream("GET", safe_url, headers=headers) as stream:
            stream.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in stream.iter_bytes():
                    handle.write(chunk)

    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )

    if safe_name.lower().endswith(".exe"):
        subprocess.Popen(
            [str(dest), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            creationflags=creationflags,
            close_fds=True,
        )
    else:
        staged_dir = UPDATES_DIR / "staged"
        shutil.rmtree(staged_dir, ignore_errors=True)
        staged_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "r") as zf:
            zf.extractall(staged_dir)

        entries = list(staged_dir.iterdir())
        source_root = entries[0] if len(entries) == 1 and entries[0].is_dir() else staged_dir

        bat_path = UPDATES_DIR / "apply_update.bat"
        pid = os.getpid()
        exe_name = Path(sys.executable).name
        bat_content = (
            "@echo off\r\n"
            "setlocal disabledelayedexpansion\r\n"
            f'set "TARGET_PID={pid}"\r\n'
            f'set "SRC_DIR={source_root}"\r\n'
            f'set "DST_DIR={APP_DIR}"\r\n'
            f'set "EXE_PATH={APP_DIR / exe_name}"\r\n'
            ":waitloop\r\n"
            'tasklist /FI "PID eq %TARGET_PID%" 2>NUL | find /I "%TARGET_PID%" >NUL\r\n'
            "if not errorlevel 1 (\r\n"
            "  timeout /t 1 /nobreak >NUL\r\n"
            "  goto waitloop\r\n"
            ")\r\n"
            'xcopy "%SRC_DIR%\\*" "%DST_DIR%\\" /E /I /Y /Q >NUL\r\n'
            'start "" "%EXE_PATH%"\r\n'
            f'rmdir /S /Q "{staged_dir}" 2>NUL\r\n'
            'del "%~f0" 2>NUL\r\n'
        )
        bat_path.write_text(bat_content, encoding="utf-8")
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            creationflags=creationflags | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )

    threading.Timer(0.8, lambda: os._exit(0)).start()
    return {
        "started": True,
        "message": "Actualización descargada. !Download se cerrará para instalar y reiniciarse automáticamente.",
    }
