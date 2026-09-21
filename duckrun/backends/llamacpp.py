"""llama.cpp backend — drives the `llama-server` binary (GGUF models)."""
from __future__ import annotations

import shutil

import httpx

from duckrun.backends.base import Backend, BackendInfo
from duckrun.server import local_http


class LlamaCppBackend(Backend):
    name = "llamacpp"

    def __init__(self, binary: str = ""):
        self.binary = binary or shutil.which("llama-server") or ""

    def detect(self) -> BackendInfo:
        if self.binary:
            return BackendInfo(name=self.name, available=True, formats=["gguf"])
        return BackendInfo(
            name=self.name,
            available=False,
            formats=["gguf"],
            reason="llama-server not found on PATH (set backends.llama_cpp_binary in config)",
        )

    def build_command(self, model_path: str, port: int, extra_args: list[str]) -> list[str]:
        return [
            self.binary,
            "-m", model_path,
            "--host", "127.0.0.1",
            "--port", str(port),
            *extra_args,
        ]

    def health_url(self, port: int) -> str:
        return f"http://127.0.0.1:{port}/health"

    def probe_loaded_model(self, port: int) -> str | None:
        try:
            r = local_http.get(f"http://127.0.0.1:{port}/v1/models", timeout=5.0)
            data = r.json().get("data", [])
            if data:
                return str(data[0].get("id"))
        except Exception:
            pass
        return None
