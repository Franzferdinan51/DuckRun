"""DuckRun configuration: YAML file + CLI overrides, with sane defaults."""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 11434,
    "data_dir": "~/.duckrun",
    "backends": {
        "llama_cpp_binary": "",
        "llama_cpp_extra_args": [],
        "mlx_extra_args": [],
        "startup_timeout": 120,
    },
}


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    return [
        Path.cwd() / "duckrun.yaml",
        here / "duckrun.yaml",
        Path(os.path.expanduser("~/.duckrun/config.yaml")),
    ]


@dataclass
class DuckRunConfig:
    host: str = "127.0.0.1"
    port: int = 11434
    data_dir: Path = field(default_factory=lambda: Path.home() / ".duckrun")
    llama_cpp_binary: str = ""
    llama_cpp_extra_args: list[str] = field(default_factory=list)
    mlx_extra_args: list[str] = field(default_factory=list)
    startup_timeout: int = 120

    @classmethod
    def load(cls, explicit_path: str | None = None, cli: argparse.Namespace | None = None) -> "DuckRunConfig":
        merged: dict = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
        paths = [Path(explicit_path)] if explicit_path else _candidate_paths()
        for p in paths:
            if p.is_file():
                merged.update(_read_file(p))
                print(f"[duckrun] config: {p}")
                break
        cfg = cls(
            host=str(merged.get("host", "127.0.0.1")),
            port=int(merged.get("port", 11434)),
            data_dir=Path(os.path.expanduser(str(merged.get("data_dir", "~/.duckrun")))),
            llama_cpp_binary=str(merged.get("backends", {}).get("llama_cpp_binary", "")),
            llama_cpp_extra_args=list(merged.get("backends", {}).get("llama_cpp_extra_args", [])),
            mlx_extra_args=list(merged.get("backends", {}).get("mlx_extra_args", [])),
            startup_timeout=int(merged.get("backends", {}).get("startup_timeout", 120)),
        )
        if cli:
            if cli.host:
                cfg.host = cli.host
            if cli.port:
                cfg.port = cli.port
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        return cfg


def _read_file(path: Path) -> dict:
    text = path.read_text()
    if yaml is not None:
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            pass
    import json

    return json.loads(text)
