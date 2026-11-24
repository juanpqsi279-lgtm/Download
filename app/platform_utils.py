"""Cross-platform OS integration helpers for !Download."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any


def get_arch_tag() -> str:
    """Return normalized CPU architecture tag ('x86_64', 'aarch64', etc.)."""
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    return machine


def spawn_detached(
    cmd: list[str],
    *,
    hide_window: bool = False,
    cwd: Path | None = None,
) -> subprocess.Popen[Any]:
    """Launch a background process detached from the current process/session."""
    kwargs: dict[str, Any] = {
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if cwd is not None:
        kwargs["cwd"] = str(cwd)

    if sys.platform == "win32":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        if hide_window:
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(cmd, **kwargs)


def open_path_in_os(target: Path) -> None:
    """Open a file or directory using the platform's default handler."""
    if sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        spawn_detached(["open", str(target)])
        return

    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        spawn_detached([xdg_open, str(target)])
        return

    gio = shutil.which("gio")
    if gio:
        spawn_detached([gio, "open", str(target)])
        return

    raise RuntimeError("No se encontró xdg-open ni gio para abrir rutas en Linux.")


def reveal_in_file_manager(target: Path) -> None:
    """Open a folder or highlight a specific file in the native file manager."""
    if sys.platform == "win32":
        if target.is_file():
            subprocess.Popen(["explorer", f"/select,{target}"])
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        if target.is_file():
            spawn_detached(["open", "-R", str(target)])
        else:
            spawn_detached(["open", str(target)])
        return

    if target.is_file():
        gdbus = shutil.which("gdbus")
        if gdbus:
            file_uri = target.resolve().as_uri().replace("'", "%27")
            try:
                completed = subprocess.run(
                    [
                        gdbus,
                        "call",
                        "--session",
                        "--dest",
                        "org.freedesktop.FileManager1",
                        "--object-path",
                        "/org/freedesktop/FileManager1",
                        "--method",
                        "org.freedesktop.FileManager1.ShowItems",
                        f"['{file_uri}']",
                        "",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    check=False,
                )
                if completed.returncode == 0:
                    return
            except Exception:
                pass
        open_path_in_os(target.parent)
        return

    open_path_in_os(target)


def open_external_url(url: str) -> bool:
    """Open an external http/https URL in the user's default browser."""
    if not url.startswith(("http://", "https://")):
        return False

    opened = False
    try:
        opened = bool(webbrowser.open(url))
    except Exception:
        opened = False

    if not opened and sys.platform.startswith("linux"):
        xdg_open = shutil.which("xdg-open")
        if xdg_open:
            spawn_detached([xdg_open, url])
            return True

    return opened
