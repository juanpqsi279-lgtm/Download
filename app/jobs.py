"""Background download job manager with progress tracking, SSE push, and desktop file saving."""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from app.config import (
    DOWNLOADS_DIR,
    FILE_TTL_SECONDS,
    MAX_CONCURRENT_DOWNLOADS,
    get_download_dir,
    is_desktop_mode,
)
from app.media_service import (
    build_download_ydl_opts,
    find_output_file,
    find_output_files,
    move_to_unique_destination,
    sanitize_folder_name,
)
from app.schemas import DownloadRequest, JobStatusResponse

TERMINAL_STATUSES = {"completed", "error", "cancelled"}


class DownloadCancelledError(Exception):
    """Raised inside yt-dlp hooks when a user cancels an active job."""


def translate_ytdlp_error(exc: Exception) -> str:
    """Convert raw yt-dlp/network exceptions into clear Spanish messages."""
    raw = str(exc or "").strip()
    lower = raw.lower()

    if "unsupported url" in lower:
        return "Este enlace o plataforma no es compatible por el momento."
    if "private video" in lower or "this video is private" in lower:
        return "Este video es privado y no se puede descargar sin acceso."
    if "drm" in lower or "widevine" in lower:
        return "Este contenido está protegido con DRM y no se puede descargar."
    if (
        "sign in to confirm" in lower
        or "login required" in lower
        or "confirm you’re not a bot" in lower
        or "not a bot" in lower
    ):
        return "La plataforma pidió inicio de sesión o verificación anti-bot para este enlace."
    if "age" in lower and ("sign in" in lower or "verify" in lower):
        return "El video tiene restricción de edad y requiere cookies de sesión."
    if "video unavailable" in lower or "this content isn't available" in lower or "not available" in lower:
        return "El contenido no está disponible, fue eliminado o está bloqueado en tu región."
    if "timed out" in lower or "timeout" in lower:
        return "La conexión tardó demasiado tiempo. Intenta nuevamente."
    if "http error 429" in lower or "too many requests" in lower:
        return "La plataforma limitó temporalmente las solicitudes (HTTP 429). Intenta en unos minutos."

    cleaned = raw.removeprefix("ERROR:").strip()
    return cleaned or "Ocurrió un error inesperado al procesar el enlace."


def _format_quality_label(req: DownloadRequest) -> str:
    if req.mode == "video":
        res = f"{req.height}p" if req.height else "Mejor"
        return f"{res} · {req.container.upper()}"
    if req.audio_format in {"flac", "wav"}:
        return f"{req.audio_format.upper()} · Sin pérdida"
    return f"{req.audio_format.upper()} · {req.audio_bitrate} kbps"


@dataclass
class JobState:
    job_id: str
    request: DownloadRequest
    job_dir: Path
    mode: str
    quality_label: str
    title: str | None = None
    status: str = "queued"
    stage: str = "En cola..."
    percent: float = 0.0
    speed: float | None = None
    eta: int | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    filename: str | None = None
    filesize: int | None = None
    saved_path: str | None = None
    is_persistent_file: bool = False
    error: str | None = None
    output_path: Path | None = None
    is_playlist: bool = False
    completed_items: int = 0
    total_items: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = field(
        default_factory=list
    )

    def to_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=self.job_id,
            status=self.status,  # type: ignore[arg-type]
            stage=self.stage,
            percent=round(self.percent, 1),
            speed=self.speed,
            eta=self.eta,
            downloaded_bytes=self.downloaded_bytes,
            total_bytes=self.total_bytes,
            filename=self.filename,
            filesize=self.filesize,
            saved_path=self.saved_path,
            title=self.title,
            mode=self.mode,
            quality_label=self.quality_label,
            error=self.error,
            created_at=self.created_at,
            is_playlist=self.is_playlist,
            completed_items=self.completed_items,
            total_items=self.total_items,
        )


class JobManager:
    """Thread-safe download job orchestrator with SSE push support and TTL cleanup."""

    def __init__(self, max_workers: int = MAX_CONCURRENT_DOWNLOADS) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="exclaim-dl-job")
        self._lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}

    def create_job(self, req: DownloadRequest) -> JobState:
        job_id = uuid.uuid4().hex[:12]
        job_dir = DOWNLOADS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        total_items = (
            len({int(i) for i in (req.playlist_items or []) if 1 <= int(i) <= 1000})
            if req.is_playlist
            else 1
        )
        job = JobState(
            job_id=job_id,
            request=req,
            job_dir=job_dir,
            mode=req.mode,
            quality_label=_format_quality_label(req),
            title=req.title_hint,
            is_playlist=req.is_playlist,
            total_items=total_items,
        )
        with self._lock:
            self._jobs[job_id] = job

        self._executor.submit(self._run_job, job_id)
        return job

    def get_job(self, job_id: str) -> JobStatusResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_response() if job else None

    def get_job_file(self, job_id: str) -> tuple[str, Path | None]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return "missing", None
            if job.status != "completed":
                return job.status, None
            return "completed", job.output_path

    def is_known_saved_file(self, candidate: Path) -> bool:
        try:
            resolved = candidate.resolve()
        except Exception:
            return False
        with self._lock:
            for job in self._jobs.values():
                if job.output_path and job.output_path.resolve() == resolved:
                    return True
        return False

    def list_recent_jobs(self, limit: int = 15) -> list[JobStatusResponse]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]
            return [job.to_response() for job in jobs]

    def cancel_job(self, job_id: str) -> JobStatusResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job.status in TERMINAL_STATUSES:
                return job.to_response()

            job.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "Descarga cancelada"
                job.updated_at = time.time()
                shutil.rmtree(job.job_dir, ignore_errors=True)
            else:
                job.stage = "Cancelando descarga..."
                job.updated_at = time.time()

            snapshot = job.to_response().model_dump()
            subs = list(job.subscribers)

        self._notify_subscribers(subs, snapshot)
        return JobStatusResponse(**snapshot)

    def subscribe(
        self, job_id: str, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue[dict[str, Any]], JobStatusResponse] | None:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            snapshot = job.to_response()
            if job.status not in TERMINAL_STATUSES:
                job.subscribers.append((loop, queue))
        return queue, snapshot

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.subscribers = [(lp, q) for lp, q in job.subscribers if q is not queue]

    def _notify_subscribers(
        self,
        subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]],
        payload: dict[str, Any],
    ) -> None:
        for loop, queue in subscribers:
            if loop.is_closed():
                continue

            def _enqueue(q: asyncio.Queue[dict[str, Any]] = queue, data: dict[str, Any] = payload) -> None:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    pass

            try:
                loop.call_soon_threadsafe(_enqueue)
            except RuntimeError:
                pass

    def _update_job(
        self,
        job_id: str,
        *,
        force_notify: bool = False,
        last_emit: list[float] | None = None,
        **fields: Any,
    ) -> None:
        now = time.monotonic()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = time.time()

            is_terminal = job.status in TERMINAL_STATUSES
            should_emit = force_notify or is_terminal
            if not should_emit and last_emit is not None:
                if now - last_emit[0] >= 0.15:
                    last_emit[0] = now
                    should_emit = True
            elif not should_emit:
                should_emit = True

            if not should_emit:
                return

            snapshot = job.to_response().model_dump()
            subs = list(job.subscribers)
            if is_terminal:
                job.subscribers.clear()

        self._notify_subscribers(subs, snapshot)

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job.cancel_event.is_set() or job.status == "cancelled":
                shutil.rmtree(job.job_dir, ignore_errors=True)
                return
            req = job.request
            job_dir = job.job_dir
            cancel_event = job.cancel_event

        job_dir.mkdir(parents=True, exist_ok=True)
        last_emit = [0.0]
        last_postprocessed_file: list[str | None] = [None]
        stream_index = [0]
        last_stream_filename = [""]

        self._update_job(
            job_id,
            force_notify=True,
            status="downloading",
            stage="Preparando descarga...",
            percent=0.0,
        )

        def progress_hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise DownloadCancelledError("Descarga cancelada por el usuario.")

            status = data.get("status")
            filename = str(data.get("filename") or "")
            if filename and filename != last_stream_filename[0]:
                last_stream_filename[0] = filename
                stream_index[0] += 1

            info_dict = data.get("info_dict") or {}
            title = info_dict.get("title")

            if status == "downloading":
                downloaded = data.get("downloaded_bytes")
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                item_percent = 0.0
                if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
                    item_percent = min(99.0, (float(downloaded) / float(total)) * 100.0)

                updates: dict[str, Any] = {
                    "status": "downloading",
                    "speed": data.get("speed"),
                    "eta": data.get("eta"),
                    "downloaded_bytes": int(downloaded) if isinstance(downloaded, (int, float)) else None,
                    "total_bytes": int(total) if isinstance(total, (int, float)) else None,
                }

                if req.is_playlist:
                    item_num = int(info_dict.get("playlist_autonumber") or info_dict.get("autonumber") or 1)
                    n_total = max(int(info_dict.get("n_entries") or 0), len(req.playlist_items or []), item_num, 1)
                    overall = min(99.0, (((item_num - 1) + (item_percent / 100.0)) / float(n_total)) * 100.0)
                    updates["percent"] = overall
                    updates["completed_items"] = max(0, item_num - 1)
                    updates["total_items"] = n_total
                    item_title = f" · {title}" if title else ""
                    updates["stage"] = f"Elemento {item_num} de {n_total}{item_title}"
                else:
                    if req.mode == "video":
                        stage = (
                            "Descargando pista de video..."
                            if stream_index[0] <= 1
                            else "Descargando pista de audio..."
                        )
                    else:
                        stage = "Descargando audio..."
                    updates["percent"] = item_percent
                    updates["stage"] = stage
                    if title:
                        updates["title"] = title
                self._update_job(job_id, last_emit=last_emit, **updates)

            elif status == "finished":
                total = data.get("total_bytes") or data.get("downloaded_bytes")
                if req.is_playlist:
                    item_num = int(info_dict.get("playlist_autonumber") or info_dict.get("autonumber") or 1)
                    n_total = max(int(info_dict.get("n_entries") or 0), len(req.playlist_items or []), item_num, 1)
                    overall = min(99.0, (float(item_num) / float(n_total)) * 100.0)
                    updates = {
                        "status": "processing",
                        "stage": f"Procesando elemento {item_num} de {n_total}...",
                        "percent": overall,
                        "completed_items": item_num,
                        "total_items": n_total,
                        "speed": None,
                        "eta": 0,
                        "downloaded_bytes": int(total) if isinstance(total, (int, float)) else None,
                        "total_bytes": int(total) if isinstance(total, (int, float)) else None,
                    }
                else:
                    updates = {
                        "status": "processing",
                        "stage": "Procesando archivo con FFmpeg...",
                        "percent": 99.0,
                        "speed": None,
                        "eta": 0,
                        "downloaded_bytes": int(total) if isinstance(total, (int, float)) else None,
                        "total_bytes": int(total) if isinstance(total, (int, float)) else None,
                    }
                    if title:
                        updates["title"] = title
                self._update_job(job_id, force_notify=True, **updates)

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise DownloadCancelledError("Descarga cancelada por el usuario.")

            pp_status = data.get("status")
            postprocessor = (data.get("postprocessor") or "").lower()
            info_dict = data.get("info_dict") or {}
            filepath = info_dict.get("filepath")
            if filepath:
                last_postprocessed_file[0] = filepath

            if pp_status == "started":
                if "extractaudio" in postprocessor:
                    stage = f"Convirtiendo audio a {req.audio_format.upper()}..."
                elif "merger" in postprocessor:
                    stage = f"Uniendo video y audio en {req.container.upper()}..."
                elif "metadata" in postprocessor:
                    stage = "Escribiendo metadatos..."
                else:
                    stage = "Finalizando archivo..."
                self._update_job(
                    job_id,
                    force_notify=True,
                    status="processing",
                    stage=stage,
                    percent=99.0,
                )

        try:
            ydl_opts = build_download_ydl_opts(req, job_dir, progress_hook, postprocessor_hook)
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(req.url, download=True)

            if cancel_event.is_set():
                raise DownloadCancelledError("Descarga cancelada por el usuario.")

            if req.is_playlist:
                files = find_output_files(job_dir)
                folder_name = sanitize_folder_name(
                    (info.get("title") if isinstance(info, dict) else None) or req.title_hint or "Playlist"
                )
                is_persistent = False
                saved_path: str | None = None

                if is_desktop_mode():
                    dest_folder = get_download_dir() / folder_name
                    dest_folder.mkdir(parents=True, exist_ok=True)
                    moved_files = [move_to_unique_destination(f, dest_folder) for f in files]
                    shutil.rmtree(job_dir, ignore_errors=True)
                    is_persistent = True
                    saved_path = str(dest_folder)
                    filesize = sum(f.stat().st_size for f in moved_files)
                    output_ref: Path = dest_folder
                    filename_val = dest_folder.name
                    count = len(moved_files)
                    stage_msg = f"¡{count} archivos guardados en {dest_folder.name}!"
                else:
                    zip_path = job_dir / f"{folder_name}.zip"
                    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
                        for f in files:
                            zf.write(f, arcname=f"{folder_name}/{f.name}")
                    for f in files:
                        f.unlink(missing_ok=True)
                    filesize = zip_path.stat().st_size
                    output_ref = zip_path
                    filename_val = zip_path.name
                    count = len(files)
                    stage_msg = f"¡Playlist lista ({count} archivos en ZIP)!"

                final_title = (
                    (info.get("title") if isinstance(info, dict) else None)
                    or req.title_hint
                    or folder_name
                )
                self._update_job(
                    job_id,
                    force_notify=True,
                    status="completed",
                    stage=stage_msg,
                    percent=100.0,
                    speed=None,
                    eta=0,
                    title=final_title,
                    filename=filename_val,
                    filesize=filesize,
                    saved_path=saved_path,
                    is_persistent_file=is_persistent,
                    output_path=output_ref,
                    completed_items=count,
                    total_items=count,
                )
                return

            if isinstance(info, dict) and info.get("_type") == "playlist":
                entries = [entry for entry in (info.get("entries") or []) if entry]
                if entries:
                    info = entries[0]

            output_file = find_output_file(job_dir, last_postprocessed_file[0])
            is_persistent = False
            saved_path = None

            if is_desktop_mode():
                output_file = move_to_unique_destination(output_file, get_download_dir())
                shutil.rmtree(job_dir, ignore_errors=True)
                is_persistent = True
                saved_path = str(output_file)

            filesize = output_file.stat().st_size
            final_title = (
                (info.get("title") if isinstance(info, dict) else None)
                or req.title_hint
                or output_file.stem
            )

            self._update_job(
                job_id,
                force_notify=True,
                status="completed",
                stage="¡Guardado en tu carpeta!" if is_persistent else "¡Descarga lista!",
                percent=100.0,
                speed=None,
                eta=0,
                title=final_title,
                filename=output_file.name,
                filesize=filesize,
                saved_path=saved_path,
                is_persistent_file=is_persistent,
                output_path=output_file,
                completed_items=1,
                total_items=1,
            )

        except DownloadCancelledError:
            shutil.rmtree(job_dir, ignore_errors=True)
            self._update_job(
                job_id,
                force_notify=True,
                status="cancelled",
                stage="Descarga cancelada",
                speed=None,
                eta=None,
            )

        except Exception as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            self._update_job(
                job_id,
                force_notify=True,
                status="error",
                stage="Error en la descarga",
                speed=None,
                eta=None,
                error=translate_ytdlp_error(exc),
            )

    def cleanup_expired_jobs(self, ttl_seconds: int = FILE_TTL_SECONDS) -> int:
        """Delete expired job entries and temp folders without touching persistent user files."""
        cutoff = time.time() - ttl_seconds
        removed = 0
        dirs_to_delete: list[Path] = []

        with self._lock:
            expired_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in TERMINAL_STATUSES and job.updated_at < cutoff
            ]
            for job_id in expired_ids:
                job = self._jobs.pop(job_id)
                dirs_to_delete.append(job.job_dir)
                removed += 1

        for job_dir in dirs_to_delete:
            shutil.rmtree(job_dir, ignore_errors=True)

        return removed

    def cleanup_stale_directories(self) -> None:
        """Remove leftover temp job directories from previous runs on startup."""
        if not DOWNLOADS_DIR.is_dir():
            return
        with self._lock:
            active_ids = set(self._jobs.keys())
        for child in DOWNLOADS_DIR.iterdir():
            if child.is_dir() and child.name not in active_ids:
                shutil.rmtree(child, ignore_errors=True)

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)


job_manager = JobManager()
