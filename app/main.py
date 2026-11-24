"""FastAPI application and REST/SSE endpoints for !Download by Juan Corporation."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    APP_DEVELOPER,
    APP_NAME,
    APP_VERSION,
    GITHUB_REPO,
    IS_FROZEN,
    STATIC_DIR,
    ensure_runtime_paths,
    get_download_dir,
    get_runtime_status,
    is_desktop_mode,
    load_settings,
    save_settings,
)
from app.jobs import TERMINAL_STATUSES, job_manager, translate_ytdlp_error
from app.media_service import extract_media_info, format_content_disposition, validate_url
from app.schemas import (
    AnalyzeRequest,
    AppUpdateRequest,
    DownloadRequest,
    JobStatusResponse,
    MediaInfoResponse,
    OpenPathRequest,
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
        "desktop_mode": is_desktop_mode(),
        "frozen": IS_FROZEN,
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
    if job_manager.is_known_saved_file(target):
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

    if target.is_file():
        subprocess.Popen(["explorer", f"/select,{target}"])
    else:
        os.startfile(str(target))  # type: ignore[attr-defined]
    return {"opened": True}


@app.post("/api/system/open-file")
async def api_open_file(req: OpenPathRequest) -> dict[str, bool]:
    if not is_desktop_mode():
        raise HTTPException(status_code=403, detail="Solo disponible en la aplicación de escritorio.")

    target = Path(req.path)
    if not _is_allowed_local_path(target):
        raise HTTPException(status_code=403, detail="Ruta fuera de las carpetas permitidas.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="El archivo ya no existe.")

    os.startfile(str(target))  # type: ignore[attr-defined]
    return {"opened": True}


@app.post("/api/info", response_model=MediaInfoResponse)
async def analyze_media(req: AnalyzeRequest) -> MediaInfoResponse:
    try:
        return await asyncio.to_thread(extract_media_info, req.url)
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
