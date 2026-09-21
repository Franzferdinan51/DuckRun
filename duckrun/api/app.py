"""DuckRun HTTP API.

OpenAI-compatible surface (drop-in for tools pointed at LM Studio/Ollama):
  GET  /v1/models
  POST /v1/chat/completions        (streaming + non-streaming)

DuckRun-native management API:
  GET  /health
  GET  /api/models                 local registry
  POST /api/models/download        {repo_id, format?} -> starts HF download
  GET  /api/downloads              download jobs + progress
  DELETE /api/models/{id}          remove model (+ files)
  GET  /api/backend/status         loaded model + backend availability
  POST /api/backend/load           {model_id} -> spawn backend child
  POST /api/backend/unload

The web UI is served from / (static files in web/).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from duckrun import __version__
from duckrun.backends.manager import EngineManager
from duckrun.config import DuckRunConfig
from duckrun.models.downloader import DownloadManager
from duckrun.models.registry import ModelRegistry

log = logging.getLogger("duckrun.api")

WEB_DIR = None  # resolved in create_app


class DownloadRequest(BaseModel):
    repo_id: str
    format: str = "auto"  # auto | gguf | mlx


class LoadRequest(BaseModel):
    model_id: str


def create_app(cfg: DuckRunConfig) -> FastAPI:
    registry = ModelRegistry(cfg.data_dir)
    downloads = DownloadManager(
        registry.models_dir,
        on_complete=lambda repo_id, fmt, path: registry.register(repo_id, fmt, path),
    )
    engine = EngineManager(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("[duckrun] api up (v%s)", __version__)
        yield
        log.info("[duckrun] shutting down, unloading model...")
        engine.unload()

    app = FastAPI(title="DuckRun", version=__version__, lifespan=lifespan)

    # -- health -----------------------------------------------------------
    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    # -- OpenAI-compatible ------------------------------------------------
    @app.get("/v1/models")
    def v1_models():
        data = [
            {
                "id": m["id"],
                "object": "model",
                "owned_by": "duckrun",
                "created": 0,
                "loaded": m["id"] == engine.active_model_id,
                "format": m["format"],
                "repo_id": m["repo_id"],
            }
            for m in registry.list()
        ]
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions")
    async def v1_chat_completions(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "JSON body must be an object")
        try:
            if body.get("stream"):
                return StreamingResponse(
                    engine.chat_stream(body), media_type="text/event-stream"
                )
            resp = await engine.chat(body)
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("[duckrun] chat proxy failed")
            raise HTTPException(502, f"backend error: {e}")

    # -- model management -------------------------------------------------
    @app.get("/api/models")
    def api_models():
        return {
            "models": registry.list(),
            "free_bytes": registry.free_bytes(),
            "loaded_model": engine.active_model_id,
        }

    @app.post("/api/models/download", status_code=202)
    def api_download(req: DownloadRequest):
        if req.format not in ("auto", "gguf", "mlx"):
            raise HTTPException(400, "format must be auto, gguf, or mlx")
        job = downloads.start(req.repo_id.strip(), req.format)
        return job.to_dict()

    @app.get("/api/downloads")
    def api_downloads():
        return {"jobs": downloads.jobs()}

    @app.delete("/api/models/{model_id}")
    def api_delete_model(model_id: str):
        if engine.active_model_id == model_id:
            engine.unload()
        if not registry.remove(model_id):
            raise HTTPException(404, f"unknown model {model_id}")
        return {"deleted": model_id}

    # -- backend control --------------------------------------------------
    @app.get("/api/backend/status")
    def api_backend_status():
        return engine.status()

    @app.post("/api/backend/load")
    def api_backend_load(req: LoadRequest):
        entry = registry.get(req.model_id)
        if not entry:
            raise HTTPException(404, f"unknown model {req.model_id}")
        try:
            return engine.load(entry["id"], entry["path"], entry["format"])
        except (ValueError, RuntimeError, TimeoutError) as e:
            raise HTTPException(409, str(e))

    @app.post("/api/backend/unload")
    def api_backend_unload():
        engine.unload()
        return {"unloaded": True}

    # -- web UI (must be mounted last so /api/* and /v1/* win) ------------
    from pathlib import Path

    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app
