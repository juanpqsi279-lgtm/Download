"""Pydantic v2 request and response schemas for !Download."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class VideoOption(BaseModel):
    id: str
    height: int | None
    width: int | None = None
    label: str
    quality_tag: str
    fps: int | None = None
    vcodec: str | None = None
    dynamic_range: str | None = None
    tbr: int | None = None
    filesize_approx: int | None = None
    has_audio: bool = False


class AudioFormatOption(BaseModel):
    format: str
    label: str
    description: str
    lossless: bool = False


class AudioBitrateOption(BaseModel):
    bitrate: int
    label: str
    estimated_bytes: int | None = None


class MediaInfoResponse(BaseModel):
    url: str
    title: str
    uploader: str | None = None
    duration: int | None = None
    duration_text: str | None = None
    upload_date: str | None = None
    like_count: int | None = None
    description: str | None = None
    webpage_url: str | None = None
    thumbnail: str | None = None
    platform: str
    view_count: int | None = None
    video_options: list[VideoOption]
    video_containers: list[dict[str, str]]
    audio_formats: list[AudioFormatOption]
    audio_bitrates: list[AudioBitrateOption]
    source_audio_abr: int | None = None
    source_audio_codec: str | None = None
    subtitle_languages: list[str] = Field(default_factory=list)
    is_live: bool = False


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    mode: Literal["video", "audio"]
    height: int | None = Field(default=None, ge=1, le=16384)
    container: Literal["mp4", "mkv", "webm"] = "mp4"
    audio_format: Literal["mp3", "m4a", "opus", "flac", "wav"] = "mp3"
    audio_bitrate: Literal[96, 128, 192, 256, 320] = 192
    embed_metadata: bool = True
    title_hint: str | None = Field(default=None, max_length=300)


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "downloading", "processing", "completed", "error", "cancelled"]
    stage: str
    percent: float = 0.0
    speed: float | None = None
    eta: int | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    filename: str | None = None
    filesize: int | None = None
    saved_path: str | None = None
    title: str | None = None
    mode: str
    quality_label: str
    error: str | None = None
    created_at: float


class SettingsUpdateRequest(BaseModel):
    download_dir: str | None = Field(default=None, max_length=512)
    theme: Literal["dark", "light", "system"] | None = None


class OpenPathRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=1024)


class AppUpdateRequest(BaseModel):
    asset_url: str = Field(..., min_length=1, max_length=2048)
    asset_name: str = Field(..., min_length=1, max_length=256)
