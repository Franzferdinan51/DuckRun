"""DuckRun backend abstraction.

A Backend is one inference engine DuckRun can drive. v1 ships two:
  - "llamacpp": the llama.cpp `llama-server` binary (GGUF models, everywhere)
  - "mlx":      Apple's MLX via `python -m mlx_lm.server` (Apple Silicon only)

(Inco Splash lands later as a third backend implementing this same interface.)

Every backend child is itself an OpenAI-compatible HTTP server, so DuckRun's
job is process supervision + request proxying, not tokenization. The Backend
interface therefore deals in model paths and child-server URLs; the
EngineManager in manager.py handles proxying /v1 traffic to the active child.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class BackendInfo:
    name: str
    available: bool
    reason: str = ""  # why unavailable, when not available
    formats: list[str] = field(default_factory=list)  # model formats it can load, e.g. ["gguf"]


class Backend(ABC):
    """Common interface every inference backend implements."""

    name: str = "base"

    @abstractmethod
    def detect(self) -> BackendInfo:
        """Is this backend usable on this machine right now? (binary present, platform OK)"""

    @abstractmethod
    def build_command(self, model_path: str, port: int, extra_args: list[str]) -> list[str]:
        """argv to launch the child server for a model."""

    @abstractmethod
    def health_url(self, port: int) -> str:
        """URL that answers 2xx/4xx once the child is ready."""

    @abstractmethod
    def probe_loaded_model(self, port: int) -> str | None:
        """Best-effort: which model id the child reports, or None."""

    # -- shared helpers -----------------------------------------------------
    def supports_format(self, fmt: str) -> bool:
        return fmt in self.detect().formats
