"""EngineManager — picks a backend for a model, supervises its child server,
and proxies OpenAI-compatible /v1 traffic (including SSE streaming) to it.

Only one model is loaded at a time in v1 (like LM Studio's single-model default).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from duckrun.backends.base import Backend, BackendInfo
from duckrun.backends.llamacpp import LlamaCppBackend
from duckrun.backends.mlx import MlxBackend
from duckrun.config import DuckRunConfig
from duckrun.server.ports import find_free_port
from duckrun.server.process import ManagedProcess

log = logging.getLogger("duckrun.engine")

FORMAT_BACKENDS = {"gguf": "llamacpp", "mlx": "mlx"}


class EngineManager:
    def __init__(self, cfg: DuckRunConfig):
        self.cfg = cfg
        self.backends: dict[str, Backend] = {
            "llamacpp": LlamaCppBackend(binary=cfg.llama_cpp_binary),
            "mlx": MlxBackend(),
        }
        self.active_backend: Backend | None = None
        self.active_model_id: str | None = None
        self.active_port: int | None = None
        self._proc: ManagedProcess | None = None
        # Loopback only — never let proxy env vars touch backend traffic.
        self._client = httpx.AsyncClient(timeout=None, trust_env=False)

    # -- introspection ------------------------------------------------------
    def backend_status(self) -> list[BackendInfo]:
        return [b.detect() for b in self.backends.values()]

    def status(self) -> dict:
        return {
            "loaded_model": self.active_model_id,
            "backend": self.active_backend.name if self.active_backend else None,
            "port": self.active_port,
            "running": self._proc.running if self._proc else False,
            "backends": [
                {"name": i.name, "available": i.available, "reason": i.reason, "formats": i.formats}
                for i in self.backend_status()
            ],
        }

    # -- lifecycle ----------------------------------------------------------
    def load(self, model_id: str, model_path: str, model_format: str) -> dict:
        backend_name = FORMAT_BACKENDS.get(model_format)
        if not backend_name:
            raise ValueError(f"unknown model format {model_format!r}")
        backend = self.backends[backend_name]
        info = backend.detect()
        if not info.available:
            raise RuntimeError(f"backend {backend_name} unavailable: {info.reason}")
        self.unload()  # v1: one model at a time
        port = find_free_port()
        extra = (
            self.cfg.llama_cpp_extra_args if backend_name == "llamacpp"
            else self.cfg.mlx_extra_args
        )
        cmd = backend.build_command(model_path, port, extra)
        proc = ManagedProcess(
            name=f"{backend_name}:{model_id}",
            cmd=cmd,
            health_url=backend.health_url(port),
            timeout=self.cfg.startup_timeout,
        )
        proc.start()  # raises on failure; nothing half-loaded left behind
        self._proc = proc
        self.active_backend = backend
        self.active_model_id = model_id
        self.active_port = port
        log.info("[duckrun] loaded %s on %s (port %d)", model_id, backend_name, port)
        return {"model": model_id, "backend": backend_name, "port": port}

    def unload(self) -> None:
        if self._proc:
            self._proc.stop()
            self._proc = None
        if self.active_model_id:
            log.info("[duckrun] unloaded %s", self.active_model_id)
        self.active_backend = None
        self.active_model_id = None
        self.active_port = None

    def shutdown(self) -> None:
        self.unload()

    # -- proxying -----------------------------------------------------------
    def _require_active(self) -> tuple[Backend, int, str]:
        if not (self.active_backend and self.active_port and self.active_model_id):
            raise RuntimeError("no model loaded — load one first via /api/backend/load")
        return self.active_backend, self.active_port, self.active_model_id

    async def chat(self, body: dict) -> httpx.Response:
        """Non-streaming passthrough to the child server."""
        _, port, model_id = self._require_active()
        body = dict(body)
        body.setdefault("model", model_id)
        r = await self._client.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=body, timeout=600.0)
        return r

    async def chat_stream(self, body: dict) -> AsyncIterator[bytes]:
        """Streaming passthrough (SSE) to the child server."""
        _, port, model_id = self._require_active()
        body = dict(body)
        body.setdefault("model", model_id)
        body["stream"] = True
        async with self._client.stream(
            "POST", f"http://127.0.0.1:{port}/v1/chat/completions", json=body, timeout=None
        ) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                yield chunk
