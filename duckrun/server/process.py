"""Supervised child-process management for inference backend servers.

Each backend (llama-server, mlx_lm.server) runs as its own HTTP server process.
ManagedProcess spawns it, tails its output into DuckRun's logs, waits for the
child's health endpoint, and shuts it down gracefully on unload/exit.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time

import httpx

from duckrun.server import local_http

log = logging.getLogger("duckrun.process")


class ManagedProcess:
    def __init__(self, name: str, cmd: list[str], health_url: str, timeout: int = 120):
        self.name = name
        self.cmd = cmd
        self.health_url = health_url
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self._tail_thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.running:
            return
        log.info("[duckrun] starting %s: %s", self.name, " ".join(self.cmd))
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._tail_thread = threading.Thread(target=self._tail, daemon=True, name=f"duckrun-{self.name}")
        self._tail_thread.start()
        self._wait_healthy()

    def _tail(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            log.info("[duckrun:%s] %s", self.name, line.rstrip())

    def _wait_healthy(self) -> None:
        deadline = time.time() + self.timeout
        last_err: Exception | None = None
        while time.time() < deadline:
            if not self.running:
                raise RuntimeError(f"{self.name} exited during startup (rc={self.proc.poll() if self.proc else '?'})")
            try:
                r = local_http.get(self.health_url, timeout=2.0)
                if r.status_code < 500:
                    log.info("[duckrun] %s healthy at %s", self.name, self.health_url)
                    return
            except Exception as e:  # still booting
                last_err = e
            time.sleep(0.5)
        self.stop()
        raise TimeoutError(f"{self.name} did not become healthy within {self.timeout}s: {last_err}")

    def stop(self, grace: float = 10.0) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        if proc.poll() is None:
            log.info("[duckrun] stopping %s (pid %s)", self.name, proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                log.warning("[duckrun] %s did not exit, killing", self.name)
                proc.kill()
                proc.wait(timeout=5)
        if self._tail_thread:
            self._tail_thread.join(timeout=2)
