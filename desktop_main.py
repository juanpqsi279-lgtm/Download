"""Native desktop entry point for !Download by Juan Corporation."""

from __future__ import annotations

import ctypes
import importlib.util
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Windowed PyInstaller binaries on Windows can have None stdout/stderr.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

if __name__ == "__main__":
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
    IS_FROZEN,
    STATIC_DIR,
    USER_DATA_DIR,
    ensure_runtime_paths,
    get_download_dir,
    load_settings,
)
from app.main import app as fastapi_app  # noqa: E402
from app.platform_utils import (  # noqa: E402
    open_external_url as os_open_external_url,
    open_path_in_os,
    reveal_in_file_manager,
    spawn_detached,
)


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


def _has_module(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _resolve_gui_backend(platform_name: str | None = None) -> str | None:
    override = (os.getenv("DOWNLOAD_GUI") or "").strip().lower()
    if override:
        return override

    plat = platform_name or sys.platform
    if plat == "win32":
        return "edgechromium"
    if plat == "darwin":
        return "cocoa"
    if plat.startswith("linux"):
        if _has_module("qtpy") and (
            _has_module("PyQt6.QtWebEngineWidgets") or _has_module("PySide6.QtWebEngineWidgets")
        ):
            return "qt"
        if _has_module("gi"):
            return "gtk"
        return None
    return None


def _prepare_linux_environment(gui: str | None) -> None:
    if sys.platform.startswith("linux") and gui == "qt":
        # Avoid Chromium sandbox crashes in AppImage, containers, and Ubuntu 24.04+ AppArmor profiles.
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")


def _build_restart_command() -> list[str]:
    appimage = os.getenv("APPIMAGE")
    if appimage:
        return [appimage, *sys.argv[1:]]
    if IS_FROZEN:
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


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


def _apply_window_theme(window: webview.Window | None, is_dark: bool) -> None:
    if window is None:
        return
    if sys.platform == "win32":
        _apply_dwm_dark_mode(window, is_dark)
        return

    if not sys.platform.startswith("linux"):
        return

    try:
        if any(mod in sys.modules for mod in ("qtpy.QtGui", "PyQt6.QtGui", "PySide6.QtGui")):
            from qtpy import QtCore, QtGui

            app = QtGui.QGuiApplication.instance()
            if app is not None:
                def _apply_qt() -> None:
                    try:
                        app.setDesktopFileName("exclaim-download")
                        hints = app.styleHints()
                        if hasattr(hints, "setColorScheme") and hasattr(QtCore.Qt, "ColorScheme"):
                            scheme = (
                                QtCore.Qt.ColorScheme.Dark
                                if is_dark
                                else QtCore.Qt.ColorScheme.Light
                            )
                            hints.setColorScheme(scheme)
                    except Exception:
                        pass

                if QtCore.QThread.currentThread() == app.thread():
                    _apply_qt()
                else:
                    QtCore.QTimer.singleShot(0, app, _apply_qt)
        elif "gi.repository.Gtk" in sys.modules:
            from gi.repository import GLib, Gtk

            def _apply_gtk() -> bool:
                try:
                    gtk_settings = Gtk.Settings.get_default()
                    if gtk_settings is not None:
                        gtk_settings.set_property("gtk-application-prefer-dark-theme", is_dark)
                except Exception:
                    pass
                return False

            GLib.idle_add(_apply_gtk)
    except Exception:
        pass


class DesktopBridge:
    """JS-Python bridge exposed as window.pywebview.api inside the native webview."""

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
        if isinstance(selected, str) and selected.strip():
            return selected
        if selected and len(selected) > 0:
            return str(selected[0])
        return None

    def open_folder(self, path: str) -> bool:
        target = Path(path)
        if not target.exists():
            return False
        try:
            reveal_in_file_manager(target)
            return True
        except Exception:
            return False

    def open_file(self, path: str) -> bool:
        target = Path(path)
        if not target.is_file():
            return False
        try:
            open_path_in_os(target)
            return True
        except Exception:
            return False

    def set_window_theme(self, theme: str) -> bool:
        if self.window is None:
            return False
        is_dark = theme != "light"
        _apply_window_theme(self.window, is_dark)
        return True

    def open_external_url(self, url: str) -> bool:
        return os_open_external_url(url)

    def restart_app(self) -> None:
        def _spawn_and_exit() -> None:
            time.sleep(0.25)
            spawn_detached(_build_restart_command())
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

    if sys.platform.startswith("linux"):
        gui_backend = _resolve_gui_backend()
        assert gui_backend is not None, (
            "No se encontró un backend gráfico en Linux (PyQt6-WebEngine o GTK/WebKit2)."
        )
        if "--check-gui" in sys.argv or IS_FROZEN:
            _prepare_linux_environment(gui_backend)
            if gui_backend == "qt":
                import webview.platforms.qt  # noqa: F401
                from qtpy import QtWebEngineWidgets  # noqa: F401
            elif gui_backend == "gtk":
                import gi  # noqa: F401
                import webview.platforms.gtk  # noqa: F401

    print("SELF-CHECK OK")
    return 0


def main() -> int:
    os.environ["DOWNLOAD_DESKTOP"] = "1"
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

        gui_backend = _resolve_gui_backend()
        if sys.platform.startswith("linux") and gui_backend is None:
            print(
                "No se detectó PyQt6-WebEngine ni GTK/WebKit2 para abrir la ventana nativa.\n"
                "Ejecuta './scripts/bootstrap.sh' para instalar el entorno de escritorio, "
                "o usa './start.sh' para abrir !Download en tu navegador.",
                file=sys.stderr,
            )
            return 1

        _prepare_linux_environment(gui_backend)

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
            _apply_window_theme(win, is_dark)

        storage_dir = USER_DATA_DIR / "webview"
        storage_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            icon_candidates = (STATIC_DIR / "icon.ico", STATIC_DIR / "icon.png")
        else:
            icon_candidates = (STATIC_DIR / "icon.png", STATIC_DIR / "icon.ico")
        icon_file = next((p for p in icon_candidates if p.is_file()), None)

        start_kwargs: dict[str, Any] = {
            "icon": str(icon_file) if icon_file is not None else None,
            "private_mode": False,
            "storage_path": str(storage_dir),
        }
        if gui_backend:
            start_kwargs["gui"] = gui_backend

        try:
            webview.start(_on_started, window, **start_kwargs)
        except Exception as exc:
            if sys.platform.startswith("linux"):
                print(
                    f"No se pudo iniciar la ventana nativa en Linux ({exc}).\n"
                    "Prueba ejecutar './scripts/bootstrap.sh' o usa './start.sh' para modo web.",
                    file=sys.stderr,
                )
                return 1
            raise
        return 0
    finally:
        server.should_exit = True
        server_thread.join(timeout=3.0)


if __name__ == "__main__":
    raise SystemExit(main())
