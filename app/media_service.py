"""yt-dlp media extraction, format selection, and download configuration for !Download."""

from __future__ import annotations

import ipaddress
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

from yt_dlp import YoutubeDL

from app.config import ensure_runtime_paths, resolve_binary, resolve_cookies_file
from app.schemas import (
    AudioBitrateOption,
    AudioFormatOption,
    DownloadRequest,
    MediaInfoResponse,
    VideoOption,
)

BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}

TEMP_SUFFIXES = {".part", ".ytdl", ".temp", ".tmp"}
IMAGE_SUFFIXES = {".webp", ".jpg", ".jpeg", ".png", ".gif"}
METADATA_SUFFIXES = {".json", ".description", ".annotations.xml"}

MONTHS_ES = {
    1: "ene",
    2: "feb",
    3: "mar",
    4: "abr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dic",
}

VIDEO_CONTAINERS: list[dict[str, str]] = [
    {"value": "mp4", "label": "MP4", "description": "Máxima compatibilidad"},
    {"value": "mkv", "label": "MKV", "description": "Contenedor universal sin recodificar"},
    {"value": "webm", "label": "WebM", "description": "Formato ligero web"},
]

AUDIO_FORMATS: list[AudioFormatOption] = [
    AudioFormatOption(
        format="mp3",
        label="MP3",
        description="Universal, funciona en cualquier reproductor",
        lossless=False,
    ),
    AudioFormatOption(
        format="m4a",
        label="M4A (AAC)",
        description="Mejor calidad por bitrate, ideal para Apple y móvil",
        lossless=False,
    ),
    AudioFormatOption(
        format="opus",
        label="Opus",
        description="Máxima eficiencia y fidelidad moderna",
        lossless=False,
    ),
    AudioFormatOption(
        format="flac",
        label="FLAC",
        description="Sin pérdida comprimido (archivos grandes)",
        lossless=True,
    ),
    AudioFormatOption(
        format="wav",
        label="WAV",
        description="Audio PCM sin compresión para edición",
        lossless=True,
    ),
]

AUDIO_BITRATES = [320, 256, 192, 128, 96]

PLATFORM_LABELS = {
    "youtube": "YouTube",
    "youtubetab": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "twitter": "X / Twitter",
    "x": "X / Twitter",
    "reddit": "Reddit",
    "twitch": "Twitch",
    "vimeo": "Vimeo",
    "soundcloud": "SoundCloud",
    "facebook": "Facebook",
    "dailymotion": "Dailymotion",
    "bilibili": "Bilibili",
    "bandcamp": "Bandcamp",
    "generic": "Enlace directo",
}


def validate_url(url: str) -> str:
    """Validate an external HTTP/HTTPS media URL and block local/private SSRF targets."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("Por favor, introduce una URL.")
    if any(ch in cleaned for ch in ("\r", "\n", "\x00")):
        raise ValueError("La URL contiene caracteres no válidos.")

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("La URL debe comenzar por http:// o https://.")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError("La URL no tiene un dominio válido.")

    hostname = parsed.hostname.lower().rstrip(".")
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise ValueError("No se permiten direcciones locales o internas.")

    host_ip = hostname.strip("[]")
    try:
        ip = ipaddress.ip_address(host_ip)
    except ValueError:
        ip = None

    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise ValueError("No se permiten direcciones IP privadas o locales.")

    return cleaned


def build_base_ydl_opts() -> dict[str, Any]:
    """Build shared yt-dlp options configured for bundled/local portable binaries."""
    ensure_runtime_paths()
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "playlist_items": "1",
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": True,
    }

    ffmpeg_path = resolve_binary("ffmpeg")
    if ffmpeg_path:
        opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

    deno_path = resolve_binary("deno")
    if deno_path:
        opts["js_runtimes"] = {"deno": {"path": deno_path}}

    cookies_path = resolve_cookies_file()
    if cookies_path is not None:
        opts["cookiefile"] = str(cookies_path)

    return opts


def format_duration(seconds: float | int | None) -> str | None:
    """Format duration seconds as MM:SS or HH:MM:SS."""
    if seconds is None:
        return None
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_upload_date(raw: str | None) -> str | None:
    """Convert YYYYMMDD date string to readable Spanish format."""
    if not raw or len(raw) != 8 or not raw.isdigit():
        return None
    year = int(raw[:4])
    month = int(raw[4:6])
    day = int(raw[6:8])
    month_label = MONTHS_ES.get(month)
    if not month_label:
        return None
    return f"{day} {month_label} {year}"


def _estimate_stream_bytes(fmt: dict[str, Any], duration: float | None) -> int | None:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if isinstance(size, (int, float)) and size > 0:
        return int(size)
    tbr = fmt.get("tbr") or fmt.get("vbr") or fmt.get("abr")
    if isinstance(tbr, (int, float)) and tbr > 0 and duration and duration > 0:
        return int(float(tbr) * float(duration) * 1000 / 8)
    return None


def _clean_vcodec(vcodec: str | None) -> str | None:
    if not vcodec or vcodec == "none":
        return None
    lower = vcodec.lower()
    if lower.startswith("avc") or "h264" in lower:
        return "H.264"
    if lower.startswith("vp09") or lower.startswith("vp9"):
        return "VP9"
    if lower.startswith("av01") or lower.startswith("av1"):
        return "AV1"
    if lower.startswith("hev") or lower.startswith("hvc") or "h265" in lower:
        return "HEVC"
    return vcodec.split(".")[0].upper()


def _clean_acodec(acodec: str | None) -> str | None:
    if not acodec or acodec == "none":
        return None
    lower = acodec.lower()
    if lower.startswith("mp4a") or "aac" in lower:
        return "AAC"
    if "opus" in lower:
        return "Opus"
    if "vorbis" in lower:
        return "Vorbis"
    if "mp3" in lower or "mp4a.40.34" in lower:
        return "MP3"
    if "flac" in lower:
        return "FLAC"
    return acodec.split(".")[0].upper()


def _clean_dynamic_range(dr: Any) -> str | None:
    if not isinstance(dr, str):
        return None
    cleaned = dr.strip().upper()
    if cleaned and cleaned not in {"SDR", "NONE"}:
        return "HDR" if "HDR" in cleaned or "HLG" in cleaned or "DV" in cleaned or "PQ" in cleaned else cleaned
    return None


def _codec_preference(vcodec: str | None) -> int:
    if not vcodec or vcodec == "none":
        return 0
    lower = vcodec.lower()
    if lower.startswith("avc") or "h264" in lower:
        return 3
    if lower.startswith("vp09") or lower.startswith("vp9"):
        return 2
    if lower.startswith("av01") or lower.startswith("av1"):
        return 1
    return 0


def _resolution_labels(height: int) -> tuple[str, str]:
    if height >= 4320:
        return f"8K ({height}p)", "8K"
    if height >= 2160:
        return f"4K ({height}p)", "4K"
    if height >= 1440:
        return f"2K ({height}p)", "2K"
    if height >= 1080:
        return f"Full HD ({height}p)", "FHD"
    if height >= 720:
        return f"HD ({height}p)", "HD"
    if height >= 480:
        return f"SD ({height}p)", "SD"
    return f"{height}p", f"{height}p"


def parse_video_options(
    formats: list[dict[str, Any]] | None,
    duration: float | None = None,
) -> tuple[list[VideoOption], int | None, str | None]:
    """Deduplicate raw yt-dlp formats by resolution and compute audio metadata."""
    valid_formats = [fmt for fmt in (formats or []) if isinstance(fmt, dict)]

    best_audio_size: int | None = None
    best_audio_abr: float = 0.0
    best_audio_codec: str | None = None

    for fmt in valid_formats:
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        if vcodec == "none" and acodec not in (None, "none"):
            abr = float(fmt.get("abr") or fmt.get("tbr") or 0)
            if abr >= best_audio_abr:
                best_audio_abr = abr
                best_audio_codec = _clean_acodec(acodec)
            est = _estimate_stream_bytes(fmt, duration)
            if est is not None and (best_audio_size is None or est > best_audio_size):
                best_audio_size = est

    source_audio_abr = int(round(best_audio_abr)) if best_audio_abr > 0 else None

    by_height: dict[int, list[dict[str, Any]]] = {}
    fallback_videos: list[dict[str, Any]] = []

    for fmt in valid_formats:
        ext = (fmt.get("ext") or "").lower()
        note = (fmt.get("format_note") or "").lower()
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        height = fmt.get("height")

        if ext == "mhtml" or "storyboard" in note or vcodec == "none":
            continue
        if vcodec is None and acodec not in (None, "none") and not height:
            continue

        if isinstance(height, (int, float)) and int(height) > 0:
            by_height.setdefault(int(height), []).append(fmt)
        else:
            fallback_videos.append(fmt)

    video_options: list[VideoOption] = []
    for height in sorted(by_height.keys(), reverse=True):
        candidates = by_height[height]
        best = max(
            candidates,
            key=lambda f: (
                int(round(float(f.get("fps") or 0))),
                _codec_preference(f.get("vcodec")),
                float(f.get("tbr") or 0),
                1 if f.get("acodec") not in (None, "none") else 0,
            ),
        )
        has_audio = best.get("acodec") not in (None, "none")
        est_size = _estimate_stream_bytes(best, duration)
        if est_size is not None and not has_audio and best_audio_size is not None:
            est_size += best_audio_size

        fps_raw = best.get("fps")
        fps = int(round(float(fps_raw))) if isinstance(fps_raw, (int, float)) and fps_raw > 0 else None
        width_raw = best.get("width")
        width = int(round(float(width_raw))) if isinstance(width_raw, (int, float)) and width_raw > 0 else None
        tbr_raw = best.get("tbr") or best.get("vbr")
        tbr = int(round(float(tbr_raw))) if isinstance(tbr_raw, (int, float)) and tbr_raw > 0 else None
        label, tag = _resolution_labels(height)

        video_options.append(
            VideoOption(
                id=f"h-{height}",
                height=height,
                width=width,
                label=label,
                quality_tag=tag,
                fps=fps,
                vcodec=_clean_vcodec(best.get("vcodec")),
                dynamic_range=_clean_dynamic_range(best.get("dynamic_range")),
                tbr=tbr,
                filesize_approx=est_size,
                has_audio=has_audio,
            )
        )

    if not video_options and fallback_videos:
        best = max(fallback_videos, key=lambda f: float(f.get("tbr") or 0))
        has_audio = best.get("acodec") not in (None, "none")
        est_size = _estimate_stream_bytes(best, duration)
        if est_size is not None and not has_audio and best_audio_size is not None:
            est_size += best_audio_size
        tbr_raw = best.get("tbr") or best.get("vbr")
        tbr = int(round(float(tbr_raw))) if isinstance(tbr_raw, (int, float)) and tbr_raw > 0 else None
        video_options.append(
            VideoOption(
                id="best",
                height=None,
                width=None,
                label="Mejor calidad disponible",
                quality_tag="MAX",
                fps=None,
                vcodec=_clean_vcodec(best.get("vcodec")),
                dynamic_range=_clean_dynamic_range(best.get("dynamic_range")),
                tbr=tbr,
                filesize_approx=est_size,
                has_audio=has_audio,
            )
        )

    return video_options, source_audio_abr, best_audio_codec


def _format_platform(extractor_key: str | None) -> str:
    if not extractor_key:
        return "Web"
    key = extractor_key.lower()
    if key in PLATFORM_LABELS:
        return PLATFORM_LABELS[key]
    for prefix, label in PLATFORM_LABELS.items():
        if key.startswith(prefix):
            return label
    return extractor_key


def _trim_description(raw: Any, limit: int = 700) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}…"


def extract_media_info(url: str) -> MediaInfoResponse:
    """Fetch metadata and available quality options without downloading media."""
    cleaned_url = validate_url(url)
    opts = {**build_base_ydl_opts(), "skip_download": True}

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(cleaned_url, download=False)

    if not info:
        raise ValueError("No se pudo obtener información del enlace proporcionado.")

    if info.get("_type") == "playlist":
        entries = [entry for entry in (info.get("entries") or []) if entry]
        if not entries:
            raise ValueError("La lista no contiene elementos disponibles.")
        info = entries[0]

    duration_raw = info.get("duration")
    duration = int(round(float(duration_raw))) if isinstance(duration_raw, (int, float)) and duration_raw >= 0 else None

    video_options, source_audio_abr, source_audio_codec = parse_video_options(info.get("formats"), duration)

    if not video_options and info.get("url"):
        ext = (info.get("ext") or "").lower()
        if ext not in {"mp3", "m4a", "opus", "ogg", "wav", "flac", "aac"}:
            video_options.append(
                VideoOption(
                    id="best",
                    height=None,
                    label="Mejor calidad disponible",
                    quality_tag="MAX",
                    filesize_approx=_estimate_stream_bytes(info, duration),
                    has_audio=True,
                )
            )

    audio_bitrates = [
        AudioBitrateOption(
            bitrate=br,
            label=f"{br} kbps",
            estimated_bytes=int(br * 1000 / 8 * duration) if duration else None,
        )
        for br in AUDIO_BITRATES
    ]

    subtitles = info.get("subtitles") or {}
    subtitle_languages = sorted(str(k) for k in subtitles.keys()) if isinstance(subtitles, dict) else []

    like_raw = info.get("like_count")
    like_count = int(like_raw) if isinstance(like_raw, (int, float)) and like_raw >= 0 else None

    return MediaInfoResponse(
        url=cleaned_url,
        title=info.get("title") or "Archivo multimedia",
        uploader=info.get("uploader") or info.get("channel") or info.get("creator"),
        duration=duration,
        duration_text=format_duration(duration),
        upload_date=format_upload_date(info.get("upload_date")),
        like_count=like_count,
        description=_trim_description(info.get("description")),
        webpage_url=info.get("webpage_url") or cleaned_url,
        thumbnail=info.get("thumbnail"),
        platform=_format_platform(info.get("extractor_key") or info.get("extractor")),
        view_count=info.get("view_count"),
        video_options=video_options,
        video_containers=VIDEO_CONTAINERS,
        audio_formats=AUDIO_FORMATS,
        audio_bitrates=audio_bitrates,
        source_audio_abr=source_audio_abr,
        source_audio_codec=source_audio_codec,
        subtitle_languages=subtitle_languages,
        is_live=bool(info.get("is_live")),
    )


def build_video_format_selector(height: int | None, container: str) -> str:
    """Build a yt-dlp format selector that preserves exact height before falling back."""
    container_lower = (container or "mp4").lower()
    if height is not None:
        if container_lower == "mp4":
            return (
                f"bestvideo[height={height}][vcodec^=avc1]+bestaudio[ext=m4a]/"
                f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height={height}]+bestaudio[ext=m4a]/"
                f"bestvideo[height={height}]+bestaudio/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        if container_lower == "webm":
            return (
                f"bestvideo[height={height}][ext=webm]+bestaudio[ext=webm]/"
                f"bestvideo[height={height}]+bestaudio/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        return (
            f"bestvideo[height={height}]+bestaudio/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/best"
        )

    if container_lower == "mp4":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    if container_lower == "webm":
        return "bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best"
    return "bestvideo+bestaudio/best"


def build_download_ydl_opts(
    req: DownloadRequest,
    job_dir: Path,
    progress_hook: Callable[[dict[str, Any]], None],
    postprocessor_hook: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Construct yt-dlp options for either video+audio muxing or audio extraction."""
    opts = build_base_ydl_opts()
    opts["outtmpl"] = str(job_dir / "%(title).120B.%(ext)s")
    opts["overwrites"] = True
    opts["progress_hooks"] = [progress_hook]
    opts["postprocessor_hooks"] = [postprocessor_hook]

    postprocessors: list[dict[str, Any]] = []

    if req.mode == "video":
        opts["format"] = build_video_format_selector(req.height, req.container)
        opts["merge_output_format"] = req.container
        if req.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
    else:
        opts["format"] = "bestaudio/best"
        quality = "0" if req.audio_format in {"flac", "wav"} else str(req.audio_bitrate)
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": req.audio_format,
                "preferredquality": quality,
            }
        )
        if req.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})

    if postprocessors:
        opts["postprocessors"] = postprocessors

    return opts


def find_output_file(job_dir: Path, hook_filepath: str | None = None) -> Path:
    """Locate the final downloaded file inside job_dir, ignoring temp artifacts."""
    if hook_filepath:
        candidate = Path(hook_filepath)
        if (
            candidate.is_file()
            and candidate.parent.resolve() == job_dir.resolve()
            and candidate.suffix.lower() not in TEMP_SUFFIXES
        ):
            return candidate

    candidates: list[Path] = []
    for item in job_dir.iterdir():
        if not item.is_file():
            continue
        lower_name = item.name.lower()
        suffix = item.suffix.lower()
        if suffix in TEMP_SUFFIXES or suffix in IMAGE_SUFFIXES or suffix in METADATA_SUFFIXES:
            continue
        if lower_name.endswith(".annotations.xml"):
            continue
        candidates.append(item)

    if not candidates:
        raise FileNotFoundError("No se encontró el archivo resultante tras la descarga.")

    return max(candidates, key=lambda p: p.stat().st_size)


def move_to_unique_destination(src: Path, dest_dir: Path) -> Path:
    """Move a finished file into dest_dir without overwriting existing files."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    if target.exists():
        counter = 1
        while True:
            candidate = dest_dir / f"{src.stem} ({counter}){src.suffix}"
            if not candidate.exists():
                target = candidate
                break
            counter += 1
    shutil.move(str(src), str(target))
    return target


def format_content_disposition(filename: str) -> str:
    """Build an ASCII-safe RFC 5987 Content-Disposition attachment header."""
    clean_name = Path(filename).name.replace("\r", "").replace("\n", "")
    stem = Path(clean_name).stem
    suffix = Path(clean_name).suffix

    ascii_stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._") or "descarga"
    ascii_suffix = re.sub(r"[^A-Za-z0-9.]+", "", suffix)
    ascii_fallback = f"{ascii_stem[:120]}{ascii_suffix}".replace('"', "")

    utf8_encoded = quote(clean_name, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"
