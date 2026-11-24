"""Two-level updater for !Download: yt-dlp zipapp override and GitHub Releases app updates."""

from __future__ import annotations

import importlib.abc
import os
import re
import shlex
import shutil
import sys
import tarfile
import threading
import zipfile
import zipimport
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import APP_DIR, APP_VERSION, GITHUB_REPO, IS_APPIMAGE, IS_FROZEN, UPDATES_DIR, can_self_update
from app.platform_utils import get_arch_tag, spawn_detached

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
        (
            a
            for a in assets
            if str(a.get("name") or "").lower().endswith(".zip")
            and not any(
                tok in str(a.get("name") or "").lower()
                for tok in ("linux", "macos", "darwin")
            )
        ),
        None,
    )


_ARCH_PATTERNS = {
    "x86_64": re.compile(r"(?:^|[^a-z0-9])(x86_64|amd64|x64|linux64)(?:$|[^a-z0-9])"),
    "aarch64": re.compile(r"(?:^|[^a-z0-9])(aarch64|arm64|linuxarm64)(?:$|[^a-z0-9])"),
}


def _linux_arch_match_score(name: str, arch: str) -> int:
    """Return 2 for matching arch, 1 for arch-agnostic name, or 0 for mismatched arch."""
    lower = name.lower()
    target_re = _ARCH_PATTERNS.get(arch)
    other_res = [pattern for key, pattern in _ARCH_PATTERNS.items() if key != arch]

    if any(pattern.search(lower) for pattern in other_res):
        return 0
    if target_re and target_re.search(lower):
        return 2
    return 1


def _pick_linux_asset(
    assets: list[dict[str, Any]],
    *,
    arch: str,
    is_appimage: bool,
    writable_app_dir: bool,
) -> dict[str, Any] | None:
    if is_appimage:
        ext_order = (".appimage", ".tar.gz", ".tgz", ".deb")
    elif writable_app_dir:
        ext_order = (".tar.gz", ".tgz", ".appimage", ".deb")
    else:
        ext_order = (".appimage", ".deb", ".tar.gz", ".tgz")

    for ext in ext_order:
        candidates: list[tuple[int, dict[str, Any]]] = []
        for asset in assets:
            name = str(asset.get("name") or "")
            if not name.lower().endswith(ext):
                continue
            score = _linux_arch_match_score(name, arch)
            if score > 0:
                candidates.append((score, asset))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]
    return None


def _pick_release_asset(
    assets: list[dict[str, Any]],
    *,
    platform_name: str | None = None,
    arch: str | None = None,
    is_appimage: bool | None = None,
    writable_app_dir: bool | None = None,
) -> dict[str, Any] | None:
    plat = platform_name or sys.platform
    if plat == "win32":
        return _pick_windows_asset(assets)
    if plat.startswith("linux"):
        resolved_arch = arch or get_arch_tag()
        resolved_appimage = IS_APPIMAGE if is_appimage is None else is_appimage
        resolved_writable = (
            (IS_FROZEN and os.access(APP_DIR, os.W_OK))
            if writable_app_dir is None
            else writable_app_dir
        )
        return _pick_linux_asset(
            assets,
            arch=resolved_arch,
            is_appimage=resolved_appimage,
            writable_app_dir=resolved_writable,
        )
    return None


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
    asset = _pick_release_asset(release.get("assets") or [])

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


def _safe_extract_tar_gz(archive_path: Path, staged_dir: Path) -> None:
    """Extract a .tar.gz archive safely, preventing path traversal outside staged_dir."""
    staged_resolved = staged_dir.resolve()
    with tarfile.open(archive_path, "r:gz") as tf:
        for member in tf.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Ruta inválida dentro de la actualización: {member.name}")
            target = (staged_resolved / member_path).resolve()
            if target != staged_resolved and staged_resolved not in target.parents:
                raise ValueError(f"Ruta fuera de destino dentro de la actualización: {member.name}")
            if member.issym() or member.islnk():
                link_target = Path(member.linkname)
                if link_target.is_absolute():
                    raise ValueError(f"Enlace absoluto no permitido: {member.name}")
                resolved_link = (target.parent / link_target).resolve()
                if resolved_link != staged_resolved and staged_resolved not in resolved_link.parents:
                    raise ValueError(f"Enlace fuera de destino: {member.name}")

        if sys.version_info >= (3, 12):
            tf.extractall(staged_dir, filter="data")
        else:
            tf.extractall(staged_dir)


def _apply_windows_update(dest: Path, safe_name: str) -> None:
    if safe_name.lower().endswith(".exe"):
        spawn_detached([str(dest), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])
        return

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
    spawn_detached(["cmd.exe", "/c", str(bat_path)], hide_window=True)


def _apply_linux_update(dest: Path, safe_name: str) -> None:
    lower_name = safe_name.lower()
    script_path = UPDATES_DIR / "apply_update.sh"
    pid = os.getpid()

    if lower_name.endswith(".appimage"):
        appimage_env = os.getenv("APPIMAGE")
        if not appimage_env:
            raise ValueError("La actualización por AppImage solo está disponible al ejecutar desde una AppImage.")
        target_appimage = Path(appimage_env).resolve()
        if not os.access(target_appimage.parent, os.W_OK):
            raise ValueError("No hay permisos de escritura en la carpeta de la AppImage actual.")

        with dest.open("rb") as handle:
            magic = handle.read(4)
        if magic != b"\x7fELF":
            dest.unlink(missing_ok=True)
            raise ValueError("El archivo AppImage descargado no es un ejecutable ELF válido.")

        os.chmod(dest, 0o755)
        script_content = "\n".join(
            [
                "#!/bin/sh",
                "set -eu",
                f"TARGET_PID={pid}",
                f"SRC_FILE={shlex.quote(str(dest))}",
                f"DST_FILE={shlex.quote(str(target_appimage))}",
                f"SCRIPT_FILE={shlex.quote(str(script_path))}",
                "i=0",
                'while kill -0 "$TARGET_PID" 2>/dev/null && [ "$i" -lt 60 ]; do',
                "  sleep 0.5",
                "  i=$((i + 1))",
                "done",
                'TMP_TARGET="${DST_FILE}.new"',
                'cp -f "$SRC_FILE" "$TMP_TARGET"',
                'chmod +x "$TMP_TARGET"',
                'mv -f "$TMP_TARGET" "$DST_FILE"',
                'rm -f "$SRC_FILE"',
                '"$DST_FILE" >/dev/null 2>&1 &',
                'rm -f "$SCRIPT_FILE"',
                "",
            ]
        )
        script_path.write_text(script_content, encoding="utf-8", newline="\n")
        os.chmod(script_path, 0o755)
        spawn_detached(["/bin/sh", str(script_path)])
        return

    if not IS_FROZEN or not os.access(APP_DIR, os.W_OK):
        raise ValueError("La carpeta de instalación actual no tiene permisos de escritura.")

    staged_dir = UPDATES_DIR / "staged"
    shutil.rmtree(staged_dir, ignore_errors=True)
    staged_dir.mkdir(parents=True, exist_ok=True)
    _safe_extract_tar_gz(dest, staged_dir)

    entries = list(staged_dir.iterdir())
    source_root = entries[0] if len(entries) == 1 and entries[0].is_dir() else staged_dir
    exe_name = Path(sys.executable).name
    exe_path = APP_DIR / exe_name

    script_content = "\n".join(
        [
            "#!/bin/sh",
            "set -eu",
            f"TARGET_PID={pid}",
            f"SRC_DIR={shlex.quote(str(source_root))}",
            f"DST_DIR={shlex.quote(str(APP_DIR))}",
            f"EXE_PATH={shlex.quote(str(exe_path))}",
            f"STAGED_DIR={shlex.quote(str(staged_dir))}",
            f"ARCHIVE_FILE={shlex.quote(str(dest))}",
            f"SCRIPT_FILE={shlex.quote(str(script_path))}",
            "i=0",
            'while kill -0 "$TARGET_PID" 2>/dev/null && [ "$i" -lt 60 ]; do',
            "  sleep 0.5",
            "  i=$((i + 1))",
            "done",
            'cp -a "$SRC_DIR/." "$DST_DIR/"',
            'chmod +x "$EXE_PATH"',
            '"$EXE_PATH" >/dev/null 2>&1 &',
            'rm -rf "$STAGED_DIR" "$ARCHIVE_FILE" "$SCRIPT_FILE"',
            "",
        ]
    )
    script_path.write_text(script_content, encoding="utf-8", newline="\n")
    os.chmod(script_path, 0o755)
    spawn_detached(["/bin/sh", str(script_path)])


def download_and_apply_app_update(asset_url: str, asset_name: str) -> dict[str, Any]:
    """Download an official release asset from GitHub and apply it cleanly."""
    if not can_self_update():
        if sys.platform.startswith("linux"):
            if IS_FROZEN:
                raise ValueError(
                    "Esta instalación (.deb o de solo lectura) debe actualizarse descargando la nueva versión desde GitHub Releases."
                )
            raise ValueError(
                "La auto-actualización automática solo funciona desde AppImage o el paquete portable Linux."
            )
        raise ValueError("La auto-actualización automática solo funciona desde el ejecutable instalado (.exe).")

    safe_url = _validate_github_asset_url(asset_url)
    safe_name = Path(asset_name or "update.bin").name
    lower_name = safe_name.lower()

    if sys.platform == "win32":
        if not lower_name.endswith((".exe", ".zip")):
            raise ValueError("El archivo de actualización debe ser un instalador .exe o paquete .zip.")
    elif sys.platform.startswith("linux"):
        if not lower_name.endswith((".appimage", ".tar.gz", ".tgz")):
            raise ValueError("El archivo de actualización en Linux debe ser .AppImage o .tar.gz.")
    else:
        raise ValueError("La auto-actualización no está soportada en esta plataforma.")

    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPDATES_DIR / safe_name
    headers = {"User-Agent": "!Download-Updater/1.0"}

    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        with client.stream("GET", safe_url, headers=headers) as stream:
            stream.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in stream.iter_bytes():
                    handle.write(chunk)

    if sys.platform == "win32":
        _apply_windows_update(dest, safe_name)
    else:
        _apply_linux_update(dest, safe_name)

    threading.Timer(0.8, lambda: os._exit(0)).start()
    return {
        "started": True,
        "message": "Actualización descargada. !Download se cerrará para instalar y reiniciarse automáticamente.",
    }
