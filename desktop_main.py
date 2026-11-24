"""Native desktop entry point for !Download by Juan Corporation."""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Windowed PyInstaller binaries on Windows can have None stdout/stderr.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

os.environ["DOWNLOAD_DESKTOP"] = "1"

# Must install any yt-dlp zipapp override before importing app.main / yt_dlp.
from app.updater import install_ytdlp_override  # noqa: E402

install_ytdlp_override()

import httpx  # noqa: E402
import uvicorn  # noqa: E402
import webview  # noqa: E402

from app.config import (  # noqa: E402
    APP_DEVELOPER,
    APP_NAME,
    STATIC_DIR,
    USER_DATA_DIR,
    ensure_runtime_paths,
    get_download_dir,
    load_settings,
)
from app.main import app as fastapi_app  # noqa: E402


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=1.5)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.12)
    raise TimeoutError("El servidor interno de !Download no respondió a tiempo.")


def _apply_dwm_dark_mode(window: webview.Window, is_dark: bool) -> None:
    if sys.platform != "win32" or window is None:
        return
    try:
        native = getattr(window, "native", None)
        if native is None or not hasattr(native, "Handle"):
            return
        hwnd = int(native.Handle.ToInt64())
        value = ctypes.c_int(1 if is_dark else 0)
        dwmapi = ctypes.windll.dwmapi
        for attr in (20, 19):
            res = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if res == 0:
                break
    except Exception:
        pass


class DesktopBridge:
    """JS-Python bridge exposed as window.pywebview.api inside WebView2."""

    def __init__(self, server: uvicorn.Server) -> None:
        self.server = server
        self.window: webview.Window | None = None

    def select_download_folder(self) -> str | None:
        if self.window is None:
            return None
        current = str(get_download_dir())
        selected = self.window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=current,
        )
        if selected and len(selected) > 0:
            return str(selected[0])
        return None

    def open_folder(self, path: str) -> bool:
        target = Path(path)
        if not target.exists():
            return False
        if target.is_file():
            subprocess.Popen(["explorer", f"/select,{target}"])
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
        return True

    def open_file(self, path: str) -> bool:
        target = Path(path)
        if not target.is_file():
            return False
        os.startfile(str(target))  # type: ignore[attr-defined]
        return True

    def set_window_theme(self, theme: str) -> bool:
        if self.window is None:
            return False
        is_dark = theme != "light"
        _apply_dwm_dark_mode(self.window, is_dark)
        return True

    def open_external_url(self, url: str) -> bool:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)
            return True
        return False

    def restart_app(self) -> None:
        def _spawn_and_exit() -> None:
            time.sleep(0.25)
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            subprocess.Popen([sys.executable, *sys.argv[1:]], creationflags=creationflags, close_fds=True)
            self.server.should_exit = True
            if self.window is not None:
                try:
                    self.window.destroy()
                except Exception:
                    pass
            os._exit(0)

        threading.Thread(target=_spawn_and_exit, daemon=True).start()


def _run_self_check(base_url: str) -> int:
    html_resp = httpx.get(f"{base_url}/", timeout=5.0)
    assert html_resp.status_code == 200, f"GET / returned {html_resp.status_code}"
    assert APP_NAME in html_resp.text, "App name missing from index.html"

    health_resp = httpx.get(f"{base_url}/api/health", timeout=5.0)
    assert health_resp.status_code == 200, f"GET /api/health returned {health_resp.status_code}"
    tools = health_resp.json()["tools"]
    for tool_key in ("yt_dlp", "ffmpeg", "ffprobe", "deno"):
        assert tools[tool_key]["available"] is True, f"Tool unavailable: {tool_key} -> {tools}"

    app_info_resp = httpx.get(f"{base_url}/api/app-info", timeout=5.0)
    assert app_info_resp.status_code == 200, f"GET /api/app-info returned {app_info_resp.status_code}"
    info = app_info_resp.json()
    assert info["name"] == APP_NAME
    assert info["developer"] == APP_DEVELOPER
    assert info["desktop_mode"] is True

    print("SELF-CHECK OK")
    return 0


def main() -> int:
    ensure_runtime_paths()
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    try:
        _wait_for_server(base_url)

        if "--self-check" in sys.argv:
            return _run_self_check(base_url)

        settings = load_settings()
        is_dark = settings.get("theme") != "light"
        bg_hex = "#07090e" if is_dark else "#edf0f6"

        bridge = DesktopBridge(server)
        window = webview.create_window(
            APP_NAME,
            url=f"{base_url}/",
            js_api=bridge,
            width=1140,
            height=840,
            min_size=(760, 620),
            background_color=bg_hex,
            text_select=True,
        )
        bridge.window = window

        def _on_started(win: webview.Window) -> None:
            _apply_dwm_dark_mode(win, is_dark)

        storage_dir = USER_DATA_DIR / "webview"
        storage_dir.mkdir(parents=True, exist_ok=True)
        icon_file = STATIC_DIR / "icon.ico"

        webview.start(
            _on_started,
            window,
            gui="edgechromium",
            icon=str(icon_file) if icon_file.is_file() else None,
            private_mode=False,
            storage_path=str(storage_dir),
        )
        return 0
    finally:
        server.should_exit = True
        server_thread.join(timeout=3.0)


if __name__ == "__main__":
    raise SystemExit(main())
