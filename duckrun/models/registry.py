"""Local model registry — the source of truth for what's on disk.

Stored as JSON at <data_dir>/models.json. Each entry:
  { "id": "mlx-community--Qwen3-4B-4bit",
    "repo_id": "mlx-community/Qwen3-4B-4bit",
    "format": "mlx" | "gguf",
    "path": "/abs/path/to/model/dir-or-file",
    "size_bytes": 123456,
    "downloaded_at": "2026-09-20T22:00:00" }
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("duckrun.registry")


def slugify_repo(repo_id: str) -> str:
    return repo_id.replace("/", "--")


class ModelRegistry:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.models_dir = data_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._file = data_dir / "models.json"
        self._models: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self._file.is_file():
            try:
                return json.loads(self._file.read_text())
            except json.JSONDecodeError:
                log.warning("[duckrun] registry corrupt, starting fresh: %s", self._file)
        return {}

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._models, indent=2))

    # -- reads --------------------------------------------------------------
    def list(self) -> list[dict]:
        return sorted(self._models.values(), key=lambda m: m["id"])

    def get(self, model_id: str) -> dict | None:
        return self._models.get(model_id)

    # -- writes -------------------------------------------------------------
    def register(self, repo_id: str, model_format: str, path: Path) -> dict:
        model_id = slugify_repo(repo_id)
        entry = {
            "id": model_id,
            "repo_id": repo_id,
            "format": model_format,
            "path": str(path),
            "size_bytes": _dir_size(path),
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._models[model_id] = entry
        self._save()
        log.info("[duckrun] registered %s (%s)", model_id, model_format)
        return entry

    def remove(self, model_id: str, delete_files: bool = True) -> bool:
        entry = self._models.pop(model_id, None)
        if entry is None:
            return False
        if delete_files:
            p = Path(entry["path"])
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink(missing_ok=True)
        self._save()
        log.info("[duckrun] removed %s", model_id)
        return True

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.models_dir).free


def _dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
