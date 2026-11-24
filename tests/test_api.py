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
