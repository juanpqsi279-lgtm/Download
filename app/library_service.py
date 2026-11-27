"""Local media library scanning, custom playlists, cover extraction, and metadata tagging."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import USER_DATA_DIR, get_download_dir, resolve_binary
from app.jobs import job_manager
from app.media_service import validate_url

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".opus", ".ogg", ".aac"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

IMPORTED_MEDIA_DIR = USER_DATA_DIR / "imported_media"
LIBRARY_REGISTRY_FILE = USER_DATA_DIR / "library_registry.json"
PLAYLISTS_FILE = USER_DATA_DIR / "playlists.json"

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_COVER_BYTES = 5 * 1024 * 1024

MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".opus": "audio/opus",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}

_NOISE_TAG_RE = re.compile(
    r"(\(|\[)\s*(official\s*(music\s*)?video|official\s*audio|lyric(s)?(\s*video)?|"
    r"visualizer|audio|video\s*oficial|letra|hd|4k|hq|explicit|remastered(\s*\d{4})?|"
    r"feat\.?[^\)\]]*)\s*(\)|\])",
    re.IGNORECASE,
)
_INDEX_PREFIX_RE = re.compile(r"^\s*\d{1,3}\s*[-._)]\s*")

_state_lock = threading.Lock()
_probe_cache: dict[tuple[str, int, int], dict[str, Any]] = {}
_cover_cache: dict[tuple[str, int], tuple[bytes, str] | None] = {}


def _subprocess_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "timeout": 25,
        "check": False,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def guess_media_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MIME_BY_EXT:
        return MIME_BY_EXT[ext]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _load_registry() -> list[str]:
    if not LIBRARY_REGISTRY_FILE.is_file():
        return []
    try:
        raw = json.loads(LIBRARY_REGISTRY_FILE.read_text(encoding="utf-8"))
        items = raw.get("imported_files") if isinstance(raw, dict) else []
        if not isinstance(items, list):
            return []
        return [str(p) for p in items if isinstance(p, str) and p.strip()]
    except Exception:
        return []


def _save_registry(paths: list[str]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    unique: list[str] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p).lower() if sys.platform == "win32" else str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    LIBRARY_REGISTRY_FILE.write_text(
        json.dumps({"imported_files": unique}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def register_external_paths(raw_paths: list[str]) -> list[dict[str, Any]]:
    """Validate and register user-selected local audio/video paths into the library."""
    with _state_lock:
        current = _load_registry()
        existing_keys = {p.lower() if sys.platform == "win32" else p for p in current}
        added: list[Path] = []
        for raw in raw_paths:
            candidate = Path(str(raw).strip())
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if not resolved.is_file() or resolved.suffix.lower() not in MEDIA_EXTS:
                continue
            resolved_str = str(resolved)
            key = resolved_str.lower() if sys.platform == "win32" else resolved_str
            if key not in existing_keys:
                existing_keys.add(key)
                current.append(resolved_str)
            added.append(resolved)
        _save_registry(current)
    return [_build_media_item(path, source="imported") for path in added]


def save_uploaded_media(filename: str, content: bytes) -> dict[str, Any]:
    """Store an uploaded audio/video file inside USER_DATA_DIR/imported_media."""
    if not content:
        raise ValueError("El archivo está vacío.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("El archivo supera el límite de 500 MB.")

    safe_name = Path(filename or "pista.mp3").name
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", safe_name).strip() or "pista.mp3"
    ext = Path(safe_name).suffix.lower()
    if ext not in MEDIA_EXTS:
        raise ValueError(f"Formato no compatible ({ext or 'sin extensión'}).")

    IMPORTED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    target = IMPORTED_MEDIA_DIR / safe_name
    if target.exists():
        stem = target.stem
        counter = 1
        while target.exists():
            target = IMPORTED_MEDIA_DIR / f"{stem} ({counter}){ext}"
            counter += 1

    target.write_bytes(content)
    return _build_media_item(target.resolve(), source="imported")


def is_allowed_media_path(target: Path) -> bool:
    """Allow local streaming/tagging only for download dir, imported dir, or registered tracks."""
    try:
        resolved = target.resolve()
    except Exception:
        return False

    if resolved.suffix.lower() not in MEDIA_EXTS:
        return False
    if job_manager.is_known_saved_file(resolved):
        return True

    for allowed_root in (get_download_dir(), IMPORTED_MEDIA_DIR):
        try:
            root_resolved = allowed_root.resolve()
            if resolved == root_resolved or root_resolved in resolved.parents:
                return True
        except Exception:
            continue

    target_key = str(resolved).lower() if sys.platform == "win32" else str(resolved)
    with _state_lock:
        for reg in _load_registry():
            try:
                reg_resolved = str(Path(reg).resolve())
                reg_key = reg_resolved.lower() if sys.platform == "win32" else reg_resolved
                if reg_key == target_key:
                    return True
            except Exception:
                continue
    return False


def _probe_media_tags(path: Path, st_mtime_ns: int, st_size: int) -> dict[str, Any]:
    cache_key = (str(path), st_mtime_ns, st_size)
    with _state_lock:
        cached = _probe_cache.get(cache_key)
    if cached is not None:
        return dict(cached)

    result: dict[str, Any] = {
        "duration": None,
        "title": None,
        "artist": None,
        "album": None,
        "year": None,
        "genre": None,
        "track": None,
        "bitrate": None,
        "codec": None,
        "has_cover": False,
    }

    ffprobe = resolve_binary("ffprobe")
    if ffprobe:
        cmd = [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            proc = subprocess.run(cmd, **_subprocess_kwargs())
            if proc.returncode == 0 and proc.stdout:
                data = json.loads(proc.stdout.decode("utf-8", errors="ignore"))
                fmt = data.get("format") or {}
                tags = {
                    str(k).lower(): str(v).strip()
                    for k, v in (fmt.get("tags") or {}).items()
                    if v is not None and str(v).strip()
                }
                dur_raw = fmt.get("duration")
                if dur_raw is not None:
                    try:
                        result["duration"] = max(0.0, float(dur_raw))
                    except (TypeError, ValueError):
                        pass
                br_raw = fmt.get("bit_rate")
                if br_raw is not None:
                    try:
                        result["bitrate"] = max(1, int(round(int(br_raw) / 1000)))
                    except (TypeError, ValueError):
                        pass

                result["title"] = tags.get("title") or None
                result["artist"] = tags.get("artist") or tags.get("album_artist") or None
                result["album"] = tags.get("album") or None
                raw_date = tags.get("date") or tags.get("year") or ""
                if raw_date:
                    year_match = re.search(r"\d{4}", raw_date)
                    result["year"] = year_match.group(0) if year_match else raw_date[:16]
                result["genre"] = tags.get("genre") or None
                result["track"] = tags.get("track") or None

                streams = data.get("streams") or []
                is_audio = path.suffix.lower() in AUDIO_EXTS
                for stream in streams:
                    disp = stream.get("disposition") or {}
                    codec_type = stream.get("codec_type")
                    if disp.get("attached_pic") == 1 or (is_audio and codec_type == "video"):
                        result["has_cover"] = True
                    if result["codec"] is None:
                        if is_audio and codec_type == "audio":
                            result["codec"] = str(stream.get("codec_name") or "").upper() or None
                        elif not is_audio and codec_type == "video":
                            result["codec"] = str(stream.get("codec_name") or "").upper() or None
        except Exception:
            pass

    with _state_lock:
        if len(_probe_cache) > 512:
            _probe_cache.clear()
        _probe_cache[cache_key] = dict(result)
    return result


def _build_media_item(
    path: Path,
    source: str,
    folder_group: str | None = None,
) -> dict[str, Any]:
    stat = path.stat()
    ext = path.suffix.lower()
    kind = "audio" if ext in AUDIO_EXTS else "video"
    meta = _probe_media_tags(path, stat.st_mtime_ns, stat.st_size)

    return {
        "path": str(path),
        "filename": path.name,
        "title": meta["title"] or path.stem,
        "artist": meta["artist"] or "",
        "album": meta["album"] or "",
        "year": meta["year"] or "",
        "genre": meta["genre"] or "",
        "track": meta["track"] or "",
        "kind": kind,
        "ext": ext.lstrip(".").upper(),
        "mime": guess_media_mime(path),
        "duration": meta["duration"],
        "bitrate": meta["bitrate"],
        "codec": meta["codec"],
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "has_cover": bool(meta["has_cover"]),
        "source": source,
        "folder_group": folder_group,
    }


def scan_library() -> list[dict[str, Any]]:
    """Scan download_dir, imported_media, and registered external files."""
    dl_dir = get_download_dir()
    items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def _add_candidate(file_path: Path, source: str, root_dir: Path | None) -> None:
        try:
            resolved = file_path.resolve()
        except Exception:
            return
        if not resolved.is_file() or resolved.suffix.lower() not in MEDIA_EXTS:
            return
        if resolved.name.startswith(".") or ".tagging_tmp" in resolved.name:
            return
        key = str(resolved).lower() if sys.platform == "win32" else str(resolved)
        if key in seen_keys:
            return
        seen_keys.add(key)
        group = None
        if root_dir is not None:
            try:
                rel = resolved.relative_to(root_dir.resolve())
                if len(rel.parts) > 1:
                    group = rel.parts[0]
            except Exception:
                group = None
        try:
            items.append(_build_media_item(resolved, source=source, folder_group=group))
        except OSError:
            return

    def _walk_limited(root: Path, source: str, max_depth: int = 3) -> None:
        if not root.is_dir():
            return
        root_res = root.resolve()
        for current_root, dirs, files in os.walk(root_res):
            curr_path = Path(current_root)
            try:
                depth = len(curr_path.relative_to(root_res).parts)
            except ValueError:
                depth = 0
            dirs[:] = [d for d in dirs if not d.startswith(".") and depth < max_depth]
            for name in files:
                _add_candidate(curr_path / name, source=source, root_dir=root_res)

    _walk_limited(dl_dir, source="downloaded", max_depth=3)
    _walk_limited(IMPORTED_MEDIA_DIR, source="imported", max_depth=2)

    with _state_lock:
        registered = _load_registry()
    valid_registered: list[str] = []
    changed_registry = False
    for reg_str in registered:
        p = Path(reg_str)
        if p.is_file():
            valid_registered.append(reg_str)
            _add_candidate(p, source="imported", root_dir=None)
        else:
            changed_registry = True
    if changed_registry:
        with _state_lock:
            _save_registry(valid_registered)

    items.sort(key=lambda item: float(item.get("mtime") or 0.0), reverse=True)
    return items


def extract_embedded_cover(path: Path) -> tuple[bytes, str] | None:
    """Extract embedded cover art from an audio file as JPEG bytes."""
    if not is_allowed_media_path(path) or not path.is_file():
        return None
    resolved = path.resolve()
    mtime_ns = resolved.stat().st_mtime_ns
    cache_key = (str(resolved), mtime_ns)
    with _state_lock:
        if cache_key in _cover_cache:
            return _cover_cache[cache_key]

    ffmpeg = resolve_binary("ffmpeg")
    cover_result: tuple[bytes, str] | None = None
    if ffmpeg:
        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(resolved),
            "-an",
            "-vcodec",
            "mjpeg",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-",
        ]
        try:
            proc = subprocess.run(cmd, **_subprocess_kwargs())
            if proc.returncode == 0 and proc.stdout and len(proc.stdout) > 64:
                cover_result = (proc.stdout, "image/jpeg")
        except Exception:
            cover_result = None

    with _state_lock:
        if len(_cover_cache) > 256:
            _cover_cache.clear()
        _cover_cache[cache_key] = cover_result
    return cover_result


def clean_track_query(raw: str) -> str:
    """Clean noisy YouTube/filename tokens into a search-friendly song query."""
    text = (raw or "").strip()
    if "." in text:
        stem = Path(text).stem
        if stem:
            text = stem
    text = _INDEX_PREFIX_RE.sub("", text)
    text = _NOISE_TAG_RE.sub(" ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\s{2,}", " ", text).strip(" -–—|")
    return text or (raw or "").strip()


def lookup_metadata_online(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """Query Apple iTunes Search API for matching song metadata and cover art."""
    cleaned = clean_track_query(query)
    if not cleaned:
        return []

    resp = httpx.get(
        "https://itunes.apple.com/search",
        params={
            "term": cleaned,
            "media": "music",
            "entity": "song",
            "limit": max(1, min(12, int(limit))),
        },
        timeout=10.0,
        headers={"User-Agent": "!Download-Metadata/1.6.0"},
    )
    resp.raise_for_status()
    payload = resp.json()
    raw_results = payload.get("results") or []

    candidates: list[dict[str, Any]] = []
    for entry in raw_results:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("trackName") or "").strip()
        artist = str(entry.get("artistName") or "").strip()
        if not title and not artist:
            continue
        art = str(entry.get("artworkUrl100") or entry.get("artworkUrl60") or "").strip()
        if art:
            art = re.sub(r"\d+x\d+bb\.", "600x600bb.", art)
        rel_date = str(entry.get("releaseDate") or "")
        year_match = re.search(r"\d{4}", rel_date)
        track_num = entry.get("trackNumber")
        track_count = entry.get("trackCount")
        if track_num and track_count:
            track_str = f"{track_num}/{track_count}"
        elif track_num:
            track_str = str(track_num)
        else:
            track_str = ""
        dur_ms = entry.get("trackTimeMillis")
        duration = round(float(dur_ms) / 1000.0, 1) if isinstance(dur_ms, (int, float)) else None

        candidates.append(
            {
                "title": title,
                "artist": artist,
                "album": str(entry.get("collectionName") or "").strip(),
                "year": year_match.group(0) if year_match else "",
                "genre": str(entry.get("primaryGenreName") or "").strip(),
                "track": track_str,
                "cover_url": art,
                "duration": duration,
            }
        )
    return candidates


def _resolve_cover_temp_file(
    cover_url: str | None,
    cover_base64: str | None,
    work_dir: Path,
) -> Path | None:
    if cover_base64 and cover_base64.strip():
        raw_b64 = cover_base64.strip()
        ext = ".jpg"
        if raw_b64.startswith("data:"):
            header, _, b64_part = raw_b64.partition(",")
            if "png" in header.lower():
                ext = ".png"
            raw_b64 = b64_part
        decoded = base64.b64decode(raw_b64, validate=False)
        if not decoded or len(decoded) > MAX_COVER_BYTES:
            raise ValueError("La imagen de carátula no es válida o supera los 5 MB.")
        out = work_dir / f"cover_{uuid.uuid4().hex[:8]}{ext}"
        out.write_bytes(decoded)
        return out

    if cover_url and cover_url.strip():
        cleaned_url = validate_url(cover_url.strip())
        resp = httpx.get(
            cleaned_url,
            timeout=12.0,
            follow_redirects=True,
            headers={"User-Agent": "!Download-Cover/1.6.0"},
        )
        if resp.status_code != 200:
            raise ValueError("No se pudo descargar la imagen de carátula seleccionada.")
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            raise ValueError("El enlace de carátula no apunta a una imagen válida.")
        if len(resp.content) > MAX_COVER_BYTES:
            raise ValueError("La imagen de carátula supera los 5 MB.")
        ext = ".png" if "png" in ctype else ".jpg"
        out = work_dir / f"cover_{uuid.uuid4().hex[:8]}{ext}"
        out.write_bytes(resp.content)
        return out

    return None


def _invalidate_caches_for(resolved: Path) -> None:
    path_str = str(resolved)
    with _state_lock:
        for k in [k for k in _probe_cache if k[0] == path_str]:
            _probe_cache.pop(k, None)
        for k in [k for k in _cover_cache if k[0] == path_str]:
            _cover_cache.pop(k, None)


def apply_audio_metadata(
    path: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    year: str | None = None,
    genre: str | None = None,
    track: str | None = None,
    cover_url: str | None = None,
    cover_base64: str | None = None,
) -> dict[str, Any]:
    """Write ID3 / MP4 / Vorbis metadata tags and cover art directly into a local audio file."""
    if not is_allowed_media_path(path):
        raise PermissionError("Ruta de archivo fuera de las carpetas permitidas.")
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError("El archivo de audio ya no existe.")
    ext = resolved.suffix.lower()
    if ext not in AUDIO_EXTS:
        raise ValueError("Solo se pueden editar metadatos en archivos de audio (.mp3, .m4a, .flac, .opus, .ogg, .wav).")

    ffmpeg = resolve_binary("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg no está disponible para guardar metadatos.")

    supports_cover = ext in {".mp3", ".m4a", ".aac", ".flac"}
    tmp_dir = Path(tempfile.mkdtemp(prefix="exclaim_tag_"))
    tmp_out = resolved.with_name(f"{resolved.stem}.tagging_tmp{resolved.suffix}")

    try:
        cover_file = _resolve_cover_temp_file(cover_url, cover_base64, tmp_dir) if supports_cover else None

        cmd: list[str] = [ffmpeg, "-y", "-v", "error", "-i", str(resolved)]
        if cover_file is not None:
            cmd.extend(["-i", str(cover_file), "-map", "0:a:0", "-map", "1:v:0", "-c:a", "copy", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"])
        elif supports_cover:
            cmd.extend(["-map", "0:a:0", "-map", "0:v?", "-c:a", "copy", "-c:v", "copy"])
        else:
            cmd.extend(["-map", "0:a:0", "-c:a", "copy"])

        meta_pairs = [
            ("title", title),
            ("artist", artist),
            ("album", album),
            ("date", year),
            ("genre", genre),
            ("track", track),
        ]
        for key, value in meta_pairs:
            if value is not None:
                cleaned = value.strip()
                cmd.extend(["-metadata", f"{key}={cleaned}"])

        if ext == ".mp3":
            cmd.extend(["-id3v2_version", "3"])
        elif ext in {".m4a", ".aac"}:
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(str(tmp_out))

        proc = subprocess.run(cmd, **_subprocess_kwargs())
        if proc.returncode != 0 or not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            err_msg = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise RuntimeError(err_msg or "FFmpeg no pudo actualizar los metadatos del archivo.")

        os.replace(tmp_out, resolved)
        _invalidate_caches_for(resolved)
        source = "imported" if IMPORTED_MEDIA_DIR.resolve() in resolved.parents else "downloaded"
        return _build_media_item(resolved, source=source)
    finally:
        if tmp_out.exists():
            try:
                tmp_out.unlink()
            except OSError:
                pass
        for leftover in tmp_dir.glob("*"):
            try:
                leftover.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


def _load_playlists_raw() -> list[dict[str, Any]]:
    if not PLAYLISTS_FILE.is_file():
        return []
    try:
        raw = json.loads(PLAYLISTS_FILE.read_text(encoding="utf-8"))
        playlists = raw.get("playlists") if isinstance(raw, dict) else []
        if isinstance(playlists, list):
            return [p for p in playlists if isinstance(p, dict) and p.get("id")]
    except Exception:
        pass
    return []


def _save_playlists_raw(playlists: list[dict[str, Any]]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PLAYLISTS_FILE.write_text(
        json.dumps({"playlists": playlists}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_playlists() -> list[dict[str, Any]]:
    with _state_lock:
        return _load_playlists_raw()


def create_playlist(name: str, kind: str = "mixed", items: list[str] | None = None) -> dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Escribe un nombre para la lista.")
    clean_kind = kind if kind in {"audio", "video", "mixed"} else "mixed"
    clean_items = [str(p).strip() for p in (items or []) if str(p).strip()]
    now = time.time()
    entry = {
        "id": uuid.uuid4().hex[:10],
        "name": clean_name[:80],
        "kind": clean_kind,
        "items": clean_items,
        "created_at": now,
        "updated_at": now,
    }
    with _state_lock:
        all_lists = _load_playlists_raw()
        all_lists.insert(0, entry)
        _save_playlists_raw(all_lists)
    return entry


def update_playlist(
    playlist_id: str,
    *,
    name: str | None = None,
    kind: str | None = None,
    items: list[str] | None = None,
) -> dict[str, Any] | None:
    with _state_lock:
        all_lists = _load_playlists_raw()
        for pl in all_lists:
            if pl.get("id") == playlist_id:
                if name is not None:
                    cleaned = name.strip()
                    if not cleaned:
                        raise ValueError("El nombre de la lista no puede estar vacío.")
                    pl["name"] = cleaned[:80]
                if kind is not None and kind in {"audio", "video", "mixed"}:
                    pl["kind"] = kind
                if items is not None:
                    pl["items"] = [str(p).strip() for p in items if str(p).strip()]
                pl["updated_at"] = time.time()
                _save_playlists_raw(all_lists)
                return pl
    return None


def delete_playlist(playlist_id: str) -> bool:
    with _state_lock:
        all_lists = _load_playlists_raw()
        filtered = [pl for pl in all_lists if pl.get("id") != playlist_id]
        if len(filtered) == len(all_lists):
            return False
        _save_playlists_raw(filtered)
        return True
