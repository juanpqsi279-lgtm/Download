"""Automated tests for !Download backend endpoints, updater, format selectors, and helpers."""

from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import APP_DEVELOPER, APP_NAME, APP_VERSION
from app.jobs import JobManager, JobState
from app.main import app
from app.media_service import (
    build_video_format_selector,
    format_content_disposition,
    move_to_unique_destination,
    parse_video_options,
    validate_url,
)
from app.schemas import DownloadRequest
from app.updater import ZipOverrideFinder, parse_semver


def test_index_returns_html() -> None:
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert APP_NAME in resp.text
    assert APP_DEVELOPER in resp.text


def test_health_and_app_info_report_tools_and_branding() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        info = client.get("/api/app-info")

    assert health.status_code == 200
    tools = health.json()["tools"]
    assert tools["yt_dlp"]["available"] is True
    assert tools["ffmpeg"]["available"] is True
    assert tools["ffprobe"]["available"] is True
    assert tools["deno"]["available"] is True

    assert info.status_code == 200
    payload = info.json()
    assert payload["name"] == APP_NAME
    assert payload["developer"] == APP_DEVELOPER
    assert payload["version"] == APP_VERSION
    assert payload["platform"] == sys.platform
    assert isinstance(payload["can_self_update"], bool)


def test_info_rejects_invalid_and_local_urls() -> None:
    with TestClient(app) as client:
        for bad_url in [
            "not-a-url",
            "file:///etc/passwd",
            "http://127.0.0.1:8000/test",
            "http://localhost:8000/test",
            "http://192.168.1.10/video.mp4",
        ]:
            resp = client.post("/api/info", json={"url": bad_url})
            assert resp.status_code == 400, f"Expected 400 for {bad_url}, got {resp.status_code}"


def test_validate_url_accepts_public_http_https() -> None:
    assert validate_url("  https://www.youtube.com/watch?v=jNQXAC9IVRw  ") == (
        "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    )


def test_parse_video_options_extracts_rich_metadata_and_adds_audio_size() -> None:
    raw_formats = [
        {"ext": "mhtml", "format_note": "storyboard", "vcodec": "none", "height": 180},
        {"ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 128, "filesize": 1_600_000},
        {
            "ext": "mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "tbr": 2500,
            "filesize": 20_000_000,
            "dynamic_range": "SDR",
        },
        {
            "ext": "webm",
            "width": 1920,
            "height": 1080,
            "fps": 60,
            "vcodec": "vp09.00.41",
            "acodec": "none",
            "tbr": 3200,
            "filesize": 24_000_000,
            "dynamic_range": "SDR",
        },
        {
            "ext": "webm",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "vp09.02.51",
            "acodec": "none",
            "tbr": 12000,
            "filesize": 80_000_000,
            "dynamic_range": "HDR10",
        },
        {
            "ext": "mp4",
            "width": 1280,
            "height": 720,
            "fps": 30,
            "vcodec": "avc1.4d401f",
            "acodec": "mp4a.40.2",
            "tbr": 1500,
            "filesize": 14_000_000,
        },
    ]
    options, abr, acodec = parse_video_options(raw_formats, duration=100)

    assert abr == 128
    assert acodec == "Opus"
    assert [opt.height for opt in options] == [2160, 1080, 720]
    assert options[0].label == "4K (2160p)"
    assert options[0].width == 3840
    assert options[0].dynamic_range == "HDR"
    assert options[0].tbr == 12000
    assert options[0].fps == 60
    assert options[0].filesize_approx == 81_600_000
    assert options[1].label == "Full HD (1080p)"
    assert options[1].fps == 60
    assert options[1].dynamic_range is None
    assert options[2].filesize_approx == 14_000_000


def test_parse_video_options_fallback_when_height_missing() -> None:
    raw_formats = [
        {"ext": "mp4", "vcodec": "h264", "acodec": "aac", "tbr": 1200},
    ]
    options, _, _ = parse_video_options(raw_formats, duration=10)
    assert len(options) == 1
    assert options[0].height is None
    assert options[0].label == "Mejor calidad disponible"
    assert options[0].filesize_approx == 1_500_000


def test_build_video_format_selector_preserves_exact_height_before_fallback() -> None:
    sel_4k_mp4 = build_video_format_selector(2160, "mp4")
    assert sel_4k_mp4.index("height=2160") < sel_4k_mp4.index("height<=2160")
    assert "bestvideo[height=2160]+bestaudio" in sel_4k_mp4

    sel_1080_mp4 = build_video_format_selector(1080, "mp4")
    assert sel_1080_mp4.startswith("bestvideo[height=1080][vcodec^=avc1]+bestaudio[ext=m4a]")

    sel_mkv = build_video_format_selector(1440, "mkv")
    assert sel_mkv.startswith("bestvideo[height=1440]+bestaudio")

    sel_webm = build_video_format_selector(720, "webm")
    assert sel_webm.startswith("bestvideo[height=720][ext=webm]+bestaudio[ext=webm]")


def test_format_content_disposition_is_pure_ascii_with_utf8_filename() -> None:
    header = format_content_disposition("Canción de prueba — ñandú 🎵.mp3")
    header.encode("latin-1")
    assert "attachment;" in header
    assert "filename*=UTF-8''" in header
    assert "%C3%B1and%C3%BA" in header


def test_missing_job_endpoints_return_404() -> None:
    with TestClient(app) as client:
        assert client.get("/api/downloads/doesnotexist").status_code == 404
        assert client.post("/api/downloads/doesnotexist/cancel").status_code == 404
        assert client.get("/api/downloads/doesnotexist/file").status_code == 404


def test_cancel_queued_job_marks_cancelled(monkeypatch) -> None:
    manager = JobManager(max_workers=1)
    monkeypatch.setattr(manager._executor, "submit", lambda *args, **kwargs: None)

    req = DownloadRequest(url="https://example.com/video", mode="audio", audio_format="mp3")
    job = manager.create_job(req)
    cancelled = manager.cancel_job(job.job_id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert not job.job_dir.exists()
    manager.shutdown()


def test_move_to_unique_destination_and_persistent_cleanup(tmp_path: Path) -> None:
    dest_dir = tmp_path / "UserDownloads"
    dest_dir.mkdir()
    (dest_dir / "clip.mp4").write_bytes(b"existing")

    temp_job_dir = tmp_path / "job_123"
    temp_job_dir.mkdir()
    src = temp_job_dir / "clip.mp4"
    src.write_bytes(b"new-video")

    moved = move_to_unique_destination(src, dest_dir)
    assert moved.name == "clip (1).mp4"
    assert moved.read_bytes() == b"new-video"
    assert (dest_dir / "clip.mp4").read_bytes() == b"existing"

    manager = JobManager(max_workers=1)
    req = DownloadRequest(url="https://example.com/v", mode="video")
    state = JobState(
        job_id="job_123",
        request=req,
        job_dir=temp_job_dir,
        mode="video",
        quality_label="1080p · MP4",
        status="completed",
        output_path=moved,
        saved_path=str(moved),
        is_persistent_file=True,
        updated_at=time.time() - 9999,
    )
    manager._jobs["job_123"] = state
    removed = manager.cleanup_expired_jobs(ttl_seconds=60)
    assert removed == 1
    assert not temp_job_dir.exists()
    assert moved.is_file()  # Persistent desktop download must NEVER be deleted
    manager.shutdown()


def test_parse_semver_and_zip_override_finder(tmp_path: Path) -> None:
    assert parse_semver("v1.2.3") > parse_semver("1.2.0")
    assert parse_semver("2026.11.24") > parse_semver("2026.11.23")

    zip_path = tmp_path / "override.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dummy_override_pkg/__init__.py", 'VERSION = "9.9.9"\n')

    finder = ZipOverrideFinder(zip_path, prefixes=("dummy_override_pkg",))
    sys.meta_path.insert(0, finder)
    try:
        import dummy_override_pkg  # type: ignore[import-not-found]

        assert dummy_override_pkg.VERSION == "9.9.9"
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("dummy_override_pkg", None)


def test_xdg_user_download_dir_parses_user_dirs(tmp_path: Path, monkeypatch) -> None:
    from app.config import _xdg_user_download_dir

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    target_dl = tmp_path / "Descargas"
    target_dl.mkdir()
    (config_dir / "user-dirs.dirs").write_text(
        '# comment\nXDG_DOWNLOAD_DIR="$HOME/Descargas"\n',
        encoding="utf-8",
    )

    assert _xdg_user_download_dir(tmp_path) == target_dl


def test_resolve_binary_posix_ignores_exe_and_non_executable(tmp_path: Path, monkeypatch) -> None:
    import app.config as cfg

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ffmpeg.exe").write_bytes(b"win")
    non_exec = bin_dir / "ffmpeg"
    non_exec.write_bytes(b"linux-no-exec")

    monkeypatch.setattr(cfg.sys, "platform", "linux")
    monkeypatch.setattr(cfg, "_candidate_bin_dirs", lambda: [bin_dir])
    monkeypatch.setattr(cfg.shutil, "which", lambda name: None)
    monkeypatch.setattr(cfg.os, "access", lambda path, mode: False)

    assert cfg.resolve_binary("ffmpeg") is None

    monkeypatch.setattr(
        cfg.os,
        "access",
        lambda path, mode: Path(path) == non_exec,
    )
    assert cfg.resolve_binary("ffmpeg") == str(non_exec)


def test_linux_open_path_and_reveal_file_manager(tmp_path: Path, monkeypatch) -> None:
    import app.platform_utils as pu

    sample_file = tmp_path / "video prueba.mp4"
    sample_file.write_bytes(b"data")

    monkeypatch.setattr(pu.sys, "platform", "linux")

    popen_calls: list[list[str]] = []

    class DummyProc:
        pass

    def fake_popen(cmd, **kwargs):
        popen_calls.append(list(cmd))
        return DummyProc()

    monkeypatch.setattr(pu.subprocess, "Popen", fake_popen)

    # 1) open_path_in_os uses xdg-open when available
    monkeypatch.setattr(pu.shutil, "which", lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None)
    pu.open_path_in_os(sample_file)
    assert popen_calls[-1] == ["/usr/bin/xdg-open", str(sample_file)]

    # 2) reveal_in_file_manager uses gdbus ShowItems when available and returning 0
    run_calls: list[list[str]] = []

    class DummyCompleted:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, **kwargs):
        run_calls.append(list(cmd))
        return DummyCompleted(0)

    monkeypatch.setattr(pu.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pu.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"gdbus", "xdg-open"} else None,
    )
    pu.reveal_in_file_manager(sample_file)
    assert run_calls
    assert "org.freedesktop.FileManager1.ShowItems" in run_calls[-1]

    # 3) reveal_in_file_manager falls back to opening parent folder when gdbus fails
    monkeypatch.setattr(pu.subprocess, "run", lambda cmd, **kwargs: DummyCompleted(1))
    pu.reveal_in_file_manager(sample_file)
    assert popen_calls[-1] == ["/usr/bin/xdg-open", str(sample_file.parent)]


def test_pick_release_asset_windows_and_linux() -> None:
    from app.updater import _pick_release_asset

    assets = [
        {"name": "Download-Setup-v1.1.0.exe", "browser_download_url": "https://github.com/a/setup.exe"},
        {"name": "Download-Portable-v1.1.0.zip", "browser_download_url": "https://github.com/a/portable.zip"},
        {"name": "Download-v1.1.0-linux-aarch64.AppImage", "browser_download_url": "https://github.com/a/arm.AppImage"},
        {"name": "Download-v1.1.0-linux-x86_64.AppImage", "browser_download_url": "https://github.com/a/x64.AppImage"},
        {"name": "Download-Portable-v1.1.0-linux-x86_64.tar.gz", "browser_download_url": "https://github.com/a/x64.tar.gz"},
        {"name": "Download-v1.1.0-linux-amd64.deb", "browser_download_url": "https://github.com/a/amd64.deb"},
    ]

    win_pick = _pick_release_asset(assets, platform_name="win32")
    assert win_pick is not None and win_pick["name"] == "Download-Setup-v1.1.0.exe"

    linux_appimage = _pick_release_asset(
        assets, platform_name="linux", arch="x86_64", is_appimage=True, writable_app_dir=False
    )
    assert linux_appimage is not None and linux_appimage["name"] == "Download-v1.1.0-linux-x86_64.AppImage"

    linux_tar = _pick_release_asset(
        assets, platform_name="linux", arch="x86_64", is_appimage=False, writable_app_dir=True
    )
    assert linux_tar is not None and linux_tar["name"] == "Download-Portable-v1.1.0-linux-x86_64.tar.gz"

    linux_arm = _pick_release_asset(
        assets, platform_name="linux", arch="aarch64", is_appimage=True, writable_app_dir=False
    )
    assert linux_arm is not None and linux_arm["name"] == "Download-v1.1.0-linux-aarch64.AppImage"

    # When only x86_64 binaries exist, aarch64 must not select an x86_64 binary
    only_x64 = [a for a in assets if "x86_64" in a["name"] or "amd64" in a["name"]]
    assert (
        _pick_release_asset(
            only_x64, platform_name="linux", arch="aarch64", is_appimage=True, writable_app_dir=False
        )
        is None
    )


def test_desktop_gui_backend_and_restart_command(monkeypatch) -> None:
    import desktop_main

    monkeypatch.delenv("DOWNLOAD_GUI", raising=False)
    assert desktop_main._resolve_gui_backend("win32") == "edgechromium"
    assert desktop_main._resolve_gui_backend("darwin") == "cocoa"

    # Linux Qt detection
    monkeypatch.setattr(
        desktop_main.importlib.util,
        "find_spec",
        lambda name: object() if name in {"qtpy", "PyQt6.QtWebEngineWidgets"} else None,
    )
    assert desktop_main._resolve_gui_backend("linux") == "qt"

    # Linux GTK fallback detection
    monkeypatch.setattr(
        desktop_main.importlib.util,
        "find_spec",
        lambda name: object() if name == "gi" else None,
    )
    assert desktop_main._resolve_gui_backend("linux") == "gtk"

    # Explicit override
    monkeypatch.setenv("DOWNLOAD_GUI", "gtk")
    assert desktop_main._resolve_gui_backend("linux") == "gtk"
    monkeypatch.delenv("DOWNLOAD_GUI", raising=False)

    # Restart command variants
    monkeypatch.setattr(desktop_main.sys, "argv", ["desktop_main.py", "--flag"])
    monkeypatch.setenv("APPIMAGE", "/tmp/Download.AppImage")
    assert desktop_main._build_restart_command() == ["/tmp/Download.AppImage", "--flag"]

    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(desktop_main, "IS_FROZEN", True)
    assert desktop_main._build_restart_command() == [sys.executable, "--flag"]

    monkeypatch.setattr(desktop_main, "IS_FROZEN", False)
    assert desktop_main._build_restart_command() == [sys.executable, "desktop_main.py", "--flag"]

    bridge = desktop_main.DesktopBridge(object())  # type: ignore[arg-type]
    public_attrs = [name for name in dir(bridge) if not name.startswith("_")]
    assert "window" not in public_attrs
    assert "server" not in public_attrs
    assert "select_media_files" in public_attrs
    assert all(callable(getattr(bridge, name)) for name in public_attrs)


def test_playlist_detection_parsing_and_download_options(tmp_path: Path) -> None:
    from app.media_service import (
        _parse_playlist_response,
        build_download_ydl_opts,
        sanitize_folder_name,
        should_extract_playlist,
        url_has_video_and_list,
    )

    normal_pl = "https://www.youtube.com/playlist?list=PL123456"
    assert url_has_video_and_list(normal_pl) is False
    assert should_extract_playlist(normal_pl, "auto") is True

    video_plus_list = "https://www.youtube.com/watch?v=abc123&list=PL123456"
    assert url_has_video_and_list(video_plus_list) is True
    assert should_extract_playlist(video_plus_list, "auto") is True
    assert should_extract_playlist(video_plus_list, "single") is False

    rd_mix = "https://www.youtube.com/watch?v=abc123&list=RDabc123"
    assert url_has_video_and_list(rd_mix) is True
    assert should_extract_playlist(rd_mix, "auto") is False
    assert should_extract_playlist(rd_mix, "playlist") is True

    raw_info = {
        "_type": "playlist",
        "title": "Mi Lista: Favoritos / 2026?",
        "uploader": "Juan",
        "extractor_key": "YoutubeTab",
        "entries": [
            {"id": "vid11111111", "title": "Pista 1", "duration": 120},
            {"id": "priv2222222", "title": "[Private video]", "duration": 90},
            None,
            {"id": "vid44444444", "title": "Pista 4", "duration": 180},
        ],
    }
    parsed = _parse_playlist_response(normal_pl, raw_info, can_toggle=False)
    assert parsed.is_playlist is True
    assert parsed.playlist_count == 2
    assert [e.index for e in parsed.playlist_entries] == [1, 4]
    assert parsed.playlist_entries[0].url == "https://www.youtube.com/watch?v=vid11111111"
    assert sanitize_folder_name("Mi Lista: Favoritos / 2026?") == "Mi Lista_ Favoritos _ 2026_"

    req = DownloadRequest(
        url=normal_pl,
        mode="audio",
        audio_format="mp3",
        audio_bitrate=192,
        is_playlist=True,
        playlist_items=[4, 1, 4],
    )
    opts = build_download_ydl_opts(req, tmp_path, lambda _: None, lambda _: None)
    assert opts["noplaylist"] is False
    assert opts["playlist_items"] == "1,4"
    assert "%(autonumber)02d" in opts["outtmpl"]


def test_altstore_source_generator_deduplicates_and_sorts() -> None:
    from scripts.generate_altstore_source import BUNDLE_ID, build_altstore_source

    v15 = build_altstore_source("v1.5.0", ipa_size=25_000_000, release_date="2026-11-25T00:00:00Z")
    v16 = build_altstore_source(
        "1.6.0",
        ipa_size=26_123_456,
        existing_data=v15,
        release_date="2026-11-26T00:00:00Z",
    )
    app_entry = v16["apps"][0]
    assert app_entry["bundleIdentifier"] == BUNDLE_ID
    assert [v["version"] for v in app_entry["versions"]] == ["1.6.0", "1.5.0"]
    assert app_entry["versions"][0]["size"] == 26_123_456
    assert app_entry["versions"][0]["downloadURL"].endswith("/v1.6.0/Download-v1.6.0-ios.ipa")


def test_library_playlists_upload_stream_and_metadata_tagging(tmp_path: Path, monkeypatch) -> None:
    import subprocess
    from app import library_service as lib
    from app.config import resolve_binary

    monkeypatch.setattr(lib, "USER_DATA_DIR", tmp_path / "userdata")
    monkeypatch.setattr(lib, "IMPORTED_MEDIA_DIR", tmp_path / "userdata" / "imported_media")
    monkeypatch.setattr(lib, "LIBRARY_REGISTRY_FILE", tmp_path / "userdata" / "library_registry.json")
    monkeypatch.setattr(lib, "PLAYLISTS_FILE", tmp_path / "userdata" / "playlists.json")
    monkeypatch.setattr(lib, "get_download_dir", lambda: tmp_path / "downloads")
    (tmp_path / "downloads").mkdir()

    assert lib.clean_track_query("01 - Mi Cancion (Official Video) [HD].mp3") == "Mi Cancion"
    assert lib.is_allowed_media_path(tmp_path / "outside.mp3") is False

    ffmpeg = resolve_binary("ffmpeg")
    assert ffmpeg is not None
    sample_mp3 = tmp_path / "src.mp3"
    proc = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.5", "-q:a", "9", str(sample_mp3)],
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0 and sample_mp3.is_file()

    with TestClient(app) as client:
        # 1) Upload external audio file
        upload = client.post(
            "/api/library/upload",
            files={"file": ("track externo.mp3", sample_mp3.read_bytes(), "audio/mpeg")},
        )
        assert upload.status_code == 200
        item = upload.json()["item"]
        track_path = item["path"]
        assert item["source"] == "imported"

        # 2) HTTP Range streaming returns 206 Partial Content
        stream_resp = client.get(
            "/api/library/stream",
            params={"path": track_path},
            headers={"Range": "bytes=0-127"},
        )
        assert stream_resp.status_code == 206
        assert len(stream_resp.content) == 128

        # 3) Apply manual metadata + tiny PNG cover
        tiny_png_b64 = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2Z0AAAAASUVORK5CYII="
        )
        tag_resp = client.post(
            "/api/library/metadata/apply",
            json={
                "path": track_path,
                "title": "Nueva Pista",
                "artist": "Artista Prueba",
                "album": "Album 2026",
                "year": "2026",
                "genre": "Pop",
                "track": "1/10",
                "cover_base64": tiny_png_b64,
            },
        )
        assert tag_resp.status_code == 200
        tagged = tag_resp.json()["item"]
        assert tagged["title"] == "Nueva Pista"
        assert tagged["artist"] == "Artista Prueba"
        assert tagged["album"] == "Album 2026"
        assert tagged["year"] == "2026"
        assert tagged["has_cover"] is True

        cover_resp = client.get("/api/library/cover", params={"path": track_path})
        assert cover_resp.status_code == 200
        assert cover_resp.headers["content-type"].startswith("image/")

        # 4) Playlist CRUD
        pl_create = client.post(
            "/api/library/playlists",
            json={"name": "Mix Audio", "kind": "audio", "items": [track_path]},
        )
        assert pl_create.status_code == 200
        pl_id = pl_create.json()["playlist"]["id"]

        pl_list = client.get("/api/library/playlists").json()["playlists"]
        assert len(pl_list) == 1 and pl_list[0]["name"] == "Mix Audio"

        pl_upd = client.put(f"/api/library/playlists/{pl_id}", json={"name": "Mix Editado"})
        assert pl_upd.status_code == 200
        assert pl_upd.json()["playlist"]["name"] == "Mix Editado"

        pl_del = client.delete(f"/api/library/playlists/{pl_id}")
        assert pl_del.status_code == 200
        assert client.get("/api/library/playlists").json()["playlists"] == []



