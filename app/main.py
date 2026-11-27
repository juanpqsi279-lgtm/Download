"""FastAPI application and REST/SSE endpoints for !Download by Juan Corporation."""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    APP_DEVELOPER,
    APP_NAME,
    APP_VERSION,
    GITHUB_REPO,
    IS_FROZEN,
    STATIC_DIR,
    can_self_update,
    ensure_runtime_paths,
    get_download_dir,
    get_runtime_status,
    is_desktop_mode,
    load_settings,
    save_settings,
)
from app.jobs import TERMINAL_STATUSES, job_manager, translate_ytdlp_error
from app.library_service import (
    add_scan_folder,
    apply_audio_metadata,
    create_playlist,
    delete_playlist,
    extract_embedded_cover,
    guess_media_mime,
    is_allowed_media_path,
    list_extra_folders,
    list_playlists,
    lookup_metadata_online,
    register_external_paths,
    remove_scan_folder,
    save_uploaded_media,
    scan_library,
    update_playlist,
)
from app.media_service import extract_media_info, format_content_disposition, validate_url
from app.platform_utils import open_path_in_os, reveal_in_file_manager
from app.schemas import (
    AnalyzeRequest,
    AppUpdateRequest,
    DownloadRequest,
    JobStatusResponse,
    LibraryRegisterRequest,
    MediaInfoResponse,
    MetadataApplyRequest,
    MetadataLookupRequest,
    OpenPathRequest,
    PlaylistCreateRequest,
    PlaylistUpdateRequest,
    SettingsUpdateRequest,
)
from app.updater import check_app_update, download_and_apply_app_update, update_ytdlp_engine

MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
CLEANUP_INTERVAL_SECONDS = 300


async def _periodic_cleanup() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await asyncio.to_thread(job_manager.cleanup_expired_jobs)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    ensure_runtime_paths()
    job_manager.cleanup_stale_directories()
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        job_manager.shutdown()


app = FastAPI(
    title=APP_NAME,
    description=f"{APP_NAME} by {APP_DEVELOPER}",
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health_check() -> dict[str, object]:
    return {"status": "ok", "tools": get_runtime_status()}


@app.get("/api/app-info")
async def app_info() -> dict[str, object]:
    return {
        "name": APP_NAME,
        "developer": APP_DEVELOPER,
        "version": APP_VERSION,
        "platform": sys.platform,
        "desktop_mode": is_desktop_mode(),
        "frozen": IS_FROZEN,
        "can_self_update": can_self_update(),
        "github_repo": GITHUB_REPO,
        "download_dir": str(get_download_dir()),
        "settings": load_settings(),
        "tools": get_runtime_status(),
    }


@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest) -> dict[str, object]:
    patch: dict[str, object] = {}
    if req.theme is not None:
        patch["theme"] = req.theme
    if req.download_dir is not None:
        candidate = Path(req.download_dir.strip())
        if not req.download_dir.strip():
            raise HTTPException(status_code=400, detail="La carpeta de descarga no puede estar vacía.")
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"No se pudo usar esa carpeta: {exc}") from exc
        patch["download_dir"] = str(candidate.resolve())

    updated = save_settings(patch)
    return {"settings": updated, "download_dir": str(get_download_dir())}


@app.get("/api/updates/check")
async def api_check_updates() -> dict[str, object]:
    return await asyncio.to_thread(check_app_update)


@app.post("/api/updates/engine")
async def api_update_engine() -> dict[str, object]:
    return await asyncio.to_thread(update_ytdlp_engine)


@app.post("/api/updates/app")
async def api_update_app(req: AppUpdateRequest) -> dict[str, object]:
    try:
        return await asyncio.to_thread(download_and_apply_app_update, req.asset_url, req.asset_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo descargar la actualización: {exc}") from exc


def _is_allowed_local_path(target: Path) -> bool:
    if job_manager.is_known_saved_file(target) or is_allowed_media_path(target):
        return True
    try:
        resolved = target.resolve()
        dl_dir = get_download_dir().resolve()
        return resolved == dl_dir or dl_dir in resolved.parents
    except Exception:
        return False


@app.post("/api/system/open-folder")
async def api_open_folder(req: OpenPathRequest) -> dict[str, bool]:
    if not is_desktop_mode():
        raise HTTPException(status_code=403, detail="Solo disponible en la aplicación de escritorio.")

    target = Path(req.path)
    if not _is_allowed_local_path(target):
        raise HTTPException(status_code=403, detail="Ruta fuera de las carpetas permitidas.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="El archivo o carpeta ya no existe.")

    try:
        reveal_in_file_manager(target)
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo abrir la carpeta: {exc}") from exc
    return {"opened": True}


@app.post("/api/system/open-file")
async def api_open_file(req: OpenPathRequest) -> dict[str, bool]:
    if not is_desktop_mode():
        raise HTTPException(status_code=403, detail="Solo disponible en la aplicación de escritorio.")

    target = Path(req.path)
    if not _is_allowed_local_path(target):
        raise HTTPException(status_code=403, detail="Ruta fuera de las carpetas permitidas.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="El archivo ya no existe.")

    try:
        open_path_in_os(target)
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo abrir el archivo: {exc}") from exc
    return {"opened": True}


@app.post("/api/info", response_model=MediaInfoResponse)
async def analyze_media(req: AnalyzeRequest) -> MediaInfoResponse:
    try:
        return await asyncio.to_thread(extract_media_info, req.url, req.playlist_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=translate_ytdlp_error(exc)) from exc


@app.get("/api/thumbnail")
async def proxy_thumbnail(url: str = Query(..., min_length=1, max_length=2048)) -> Response:
    try:
        cleaned_url = validate_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(cleaned_url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="No se pudo descargar la miniatura.") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="La plataforma rechazó la carga de la miniatura.")

    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="El recurso no corresponde a una imagen válida.")

    if len(resp.content) > MAX_THUMBNAIL_BYTES:
        raise HTTPException(status_code=413, detail="La miniatura supera el tamaño permitido.")

    return Response(
        content=resp.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/downloads", response_model=JobStatusResponse)
async def create_download(req: DownloadRequest) -> JobStatusResponse:
    try:
        cleaned_url = validate_url(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_req = req.model_copy(update={"url": cleaned_url})
    job = job_manager.create_job(normalized_req)
    return job.to_response()


@app.get("/api/downloads", response_model=list[JobStatusResponse])
async def list_downloads() -> list[JobStatusResponse]:
    return job_manager.list_recent_jobs()


@app.get("/api/downloads/{job_id}", response_model=JobStatusResponse)
async def get_download_status(job_id: str) -> JobStatusResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Descarga no encontrada.")
    return job


@app.get("/api/downloads/{job_id}/events")
async def stream_download_events(job_id: str) -> StreamingResponse:
    loop = asyncio.get_running_loop()
    subscription = job_manager.subscribe(job_id, loop)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Descarga no encontrada.")

    queue, initial_snapshot = subscription

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps(initial_snapshot.model_dump())}\n\n"
            if initial_snapshot.status in TERMINAL_STATUSES:
                return

            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                yield f"data: {json.dumps(event_data)}\n\n"
                if event_data.get("status") in TERMINAL_STATUSES:
                    break
        finally:
            job_manager.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/downloads/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_download(job_id: str) -> JobStatusResponse:
    job = job_manager.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Descarga no encontrada.")
    return job


@app.get("/api/downloads/{job_id}/file")
async def download_completed_file(job_id: str) -> FileResponse:
    status, output_path = job_manager.get_job_file(job_id)
    if status == "missing":
        raise HTTPException(status_code=404, detail="Descarga no encontrada o expirada.")
    if status != "completed":
        raise HTTPException(status_code=409, detail="El archivo aún no está listo para descargar.")
    if output_path is None or not output_path.is_file():
        raise HTTPException(status_code=410, detail="El archivo temporal ya expiró o fue eliminado.")

    return FileResponse(
        path=output_path,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": format_content_disposition(output_path.name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/library/files")
async def api_library_files(scope: str = Query(default="all")) -> dict[str, object]:
    items = await asyncio.to_thread(scan_library, scope)
    return {
        "items": items,
        "download_dir": str(get_download_dir()),
        "extra_folders": list_extra_folders(),
        "media_permission_granted": True,
    }


@app.post("/api/library/folders")
async def api_library_add_folder(req: OpenPathRequest) -> dict[str, object]:
    try:
        folders = await asyncio.to_thread(add_scan_folder, req.path)
        return {"extra_folders": folders}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/library/folders")
async def api_library_remove_folder(path: str = Query(..., min_length=1, max_length=1024)) -> dict[str, object]:
    folders = await asyncio.to_thread(remove_scan_folder, path)
    return {"extra_folders": folders}


@app.post("/api/library/register")
async def api_library_register(req: LibraryRegisterRequest) -> dict[str, object]:
    items = await asyncio.to_thread(register_external_paths, req.paths)
    return {"added": items}


@app.post("/api/library/upload")
async def api_library_upload(request: Request) -> dict[str, object]:
    from urllib.parse import unquote
    import re

    raw = await request.body()
    content_type = request.headers.get("content-type", "")
    filename = unquote(request.headers.get("x-filename", "pista.mp3"))

    if "multipart/form-data" in content_type.lower() and "boundary=" in content_type:
        boundary = content_type.split("boundary=", 1)[1].split(";", 1)[0].strip().strip('"')
        marker = f"--{boundary}".encode("ascii", errors="ignore")
        parts = raw.split(marker)
        extracted_bytes: bytes | None = None
        for part in parts:
            if b"Content-Disposition:" in part and b"\r\n\r\n" in part:
                hdr, _, body = part.partition(b"\r\n\r\n")
                hdr_text = hdr.decode("utf-8", errors="ignore")
                m = re.search(r'filename="([^"]+)"', hdr_text)
                if m:
                    filename = m.group(1)
                    extracted_bytes = body.removesuffix(b"\r\n")
                    break
        if extracted_bytes is None:
            raise HTTPException(status_code=400, detail="No se recibió ningún archivo en la petición.")
        raw = extracted_bytes

    try:
        item = await asyncio.to_thread(save_uploaded_media, filename, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.get("/api/library/stream")
async def api_library_stream(path: str = Query(..., min_length=1, max_length=1024)) -> FileResponse:
    target = Path(path)
    if not is_allowed_media_path(target):
        raise HTTPException(status_code=403, detail="Archivo fuera de las carpetas permitidas.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="El archivo multimedia no existe.")
    return FileResponse(
        path=target,
        media_type=guess_media_mime(target),
        headers={"X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes"},
    )


@app.get("/api/library/cover")
async def api_library_cover(path: str = Query(..., min_length=1, max_length=1024)) -> Response:
    target = Path(path)
    if not is_allowed_media_path(target):
        raise HTTPException(status_code=403, detail="Archivo fuera de las carpetas permitidas.")
    cover = await asyncio.to_thread(extract_embedded_cover, target)
    if cover is None:
        raise HTTPException(status_code=404, detail="Sin carátula embebida.")
    img_bytes, mime_type = cover
    return Response(
        content=img_bytes,
        media_type=mime_type,
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/library/metadata/auto")
async def api_metadata_auto(req: MetadataLookupRequest) -> dict[str, object]:
    try:
        candidates = await asyncio.to_thread(lookup_metadata_online, req.query, req.limit)
        return {"results": candidates}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo buscar metadatos en línea: {exc}") from exc


@app.post("/api/library/metadata/apply")
async def api_metadata_apply(req: MetadataApplyRequest) -> dict[str, object]:
    target = Path(req.path)
    try:
        updated = await asyncio.to_thread(
            apply_audio_metadata,
            target,
            title=req.title,
            artist=req.artist,
            album=req.album,
            year=req.year,
            genre=req.genre,
            track=req.track,
            cover_url=req.cover_url,
            cover_base64=req.cover_base64,
        )
        return {"item": updated}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudieron guardar los metadatos: {exc}") from exc


@app.get("/api/library/playlists")
async def api_library_playlists() -> dict[str, object]:
    return {"playlists": list_playlists()}


@app.post("/api/library/playlists")
async def api_library_create_playlist(req: PlaylistCreateRequest) -> dict[str, object]:
    try:
        created = create_playlist(req.name, req.kind, req.items)
        return {"playlist": created}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/library/playlists/{playlist_id}")
async def api_library_update_playlist(playlist_id: str, req: PlaylistUpdateRequest) -> dict[str, object]:
    try:
        updated = update_playlist(playlist_id, name=req.name, kind=req.kind, items=req.items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Lista de reproducción no encontrada.")
    return {"playlist": updated}


@app.delete("/api/library/playlists/{playlist_id}")
async def api_library_delete_playlist(playlist_id: str) -> dict[str, bool]:
    if not delete_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Lista de reproducción no encontrada.")
    return {"deleted": True}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
