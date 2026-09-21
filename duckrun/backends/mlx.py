"""MLX backend — drives `python -m mlx_lm.server` (Apple Silicon only)."""
from __future__ import annotations

import importlib.util
import platform
import sys

import httpx

from duckrun.backends.base import Backend, BackendInfo
from duckrun.server import local_http


class MlxBackend(Backend):
    name = "mlx"

    def detect(self) -> BackendInfo:
        if not (sys.platform == "darwin" and platform.machine() == "arm64"):
            return BackendInfo(
                name=self.name, available=False, formats=["mlx"],
                reason=f"MLX needs Apple Silicon macOS (this is {sys.platform}/{platform.machine()})",
            )
        if importlib.util.find_spec("mlx_lm") is None:
            return BackendInfo(
                name=self.name, available=False, formats=["mlx"],
                reason="mlx_lm not installed (pip install mlx-lm)",
            )
        return BackendInfo(name=self.name, available=True, formats=["mlx"])

    def build_command(self, model_path: str, port: int, extra_args: list[str]) -> list[str]:
        return [
            sys.executable, "-m", "mlx_lm.server",
            "--model", model_path,
            "--port", str(port),
            *extra_args,
        ]

    def health_url(self, port: int) -> str:
        # mlx_lm.server has no /health; /v1/models 200s once ready.
        return f"http://127.0.0.1:{port}/v1/models"

    def probe_loaded_model(self, port: int) -> str | None:
        try:
            r = local_http.get(f"http://127.0.0.1:{port}/v1/models", timeout=5.0)
            data = r.json().get("data", [])
            if data:
                return str(data[0].get("id"))
        except Exception:
            pass
        return None
