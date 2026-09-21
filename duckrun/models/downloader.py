"""Hugging Face Hub downloads with live progress.

Runs each download on a worker thread (huggingface_hub is blocking), tracks
per-file byte progress, and exposes it via jobs()/progress() for the API to poll.
No secrets involved — public repos need no token; set HF_TOKEN in the
environment yourself if you pull gated repos.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("duckrun.downloads")


def _sanitize_no_proxy() -> None:
    """Drop IPv6 literals from no_proxy/NO_PROXY.

    Some httpx versions crash parsing any IPv6 entry here — even bracketed
    `[::1]` — because they split host:port on colons. DuckRun's own loopback
    clients use trust_env=False anyway, and HF traffic never targets loopback,
    so dropping these entries is behavior-preserving.
    """
    import os

    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key)
        if not val:
            continue
        kept = [e for e in val.split(",") if ":" not in e]
        if len(kept) != len(val.split(",")):
            os.environ[key] = ",".join(kept)
            log.info("[duckrun] sanitized %s for httpx compatibility", key)


class DownloadJob:
    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.state = "queued"  # queued -> downloading -> done | error
        self.total_bytes = 0
        self.done_bytes = 0
        self.current_file = ""
        self.error = ""
        self.model_id = ""

    @property
    def progress(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.done_bytes / self.total_bytes)

    def to_dict(self) -> dict:
        return {
            "repo_id": self.repo_id,
            "model_id": self.model_id,
            "state": self.state,
            "progress": round(self.progress, 4),
            "done_bytes": self.done_bytes,
            "total_bytes": self.total_bytes,
            "current_file": self.current_file,
            "error": self.error,
        }


def _pick_single_gguf(files: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """GGUF repos usually ship many quants; llama-server loads exactly one file.

    Prefer Q4_K_M (the standard size/quality default), else take the largest
    single .gguf (least-quantized). Returns a one-element list.
    """
    if len(files) <= 1:
        return files
    for fname, fsize in files:
        if "q4_k_m" in fname.lower():
            log.info("[duckrun] gguf: %d quants available, picking Q4_K_M (%s)",
                     len(files), fname)
            return [(fname, fsize)]
    fname, fsize = max(files, key=lambda fs: fs[1])
    log.info("[duckrun] gguf: %d quants available, no Q4_K_M, picking largest (%s)",
             len(files), fname)
    return [(fname, fsize)]


class DownloadManager:
    def __init__(self, models_dir: Path, on_complete=None):
        _sanitize_no_proxy()
        self.models_dir = models_dir
        self.on_complete = on_complete  # fn(repo_id, format, path) -> entry dict
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()

    # -- API surface --------------------------------------------------------
    def start(self, repo_id: str, model_format: str = "auto") -> DownloadJob:
        from duckrun.models.registry import slugify_repo

        model_id = slugify_repo(repo_id)
        with self._lock:
            existing = self._jobs.get(model_id)
            if existing and existing.state in ("queued", "downloading"):
                return existing
            job = DownloadJob(repo_id)
            job.model_id = model_id
            self._jobs[model_id] = job
        t = threading.Thread(
            target=self._run, args=(job, model_format), daemon=True, name=f"duckrun-dl-{model_id}"
        )
        t.start()
        return job

    def jobs(self) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()]

    def get(self, model_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(model_id)

    # -- worker -------------------------------------------------------------
    def _run(self, job: DownloadJob, model_format: str) -> None:
        try:
            from huggingface_hub import HfApi, hf_hub_download

            api = HfApi()
            info = api.model_info(job.repo_id, files_metadata=True)
            files = [(s.rfilename, s.size or 0) for s in (info.siblings or [])]
            if model_format == "gguf":
                files = [(f, s) for f, s in files if f.endswith(".gguf")]
                files = _pick_single_gguf(files)
            elif model_format == "mlx":
                files = [(f, s) for f, s in files if not f.endswith(".gguf")]
            if not files:
                raise ValueError(f"no files match format={model_format} in {job.repo_id}")

            job.total_bytes = sum(s for _, s in files)
            job.state = "downloading"
            log.info("[duckrun] downloading %s (%d files, %.1f GB)",
                     job.repo_id, len(files), job.total_bytes / 1e9)

            dest = self.models_dir / job.model_id
            for fname, fsize in files:
                job.current_file = fname
                before = job.done_bytes
                hf_hub_download(
                    repo_id=job.repo_id,
                    filename=fname,
                    local_dir=dest,
                    local_dir_use_symlinks=False,
                )
                # hf_hub_download is atomic per file; credit the file's full size.
                job.done_bytes = before + fsize

            detected = model_format
            if detected == "auto":
                detected = "gguf" if any(f.endswith(".gguf") for f, _ in files) else "mlx"
            model_path = dest
            if detected == "gguf" and len(files) == 1:
                # llama-server takes a single model file, not a directory
                model_path = dest / files[0][0]
            entry = self.on_complete(job.repo_id, detected, model_path) if self.on_complete else {}
            job.model_id = entry.get("id", job.model_id) if entry else job.model_id
            job.state = "done"
            log.info("[duckrun] download complete: %s", job.repo_id)
        except Exception as e:  # noqa: BLE001 — surfaced on the job for the UI
            job.state = "error"
            job.error = str(e)
            log.error("[duckrun] download failed for %s: %s", job.repo_id, e)
