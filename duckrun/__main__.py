"""`python -m duckrun` — start the DuckRun server."""
from __future__ import annotations

import argparse
import sys

import uvicorn

from duckrun import __version__
from duckrun.api.app import create_app
from duckrun.config import DuckRunConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="duckrun", description="DuckRun — your own local AI app")
    p.add_argument("--host", default=None, help="bind host (default from config: 127.0.0.1)")
    p.add_argument("--port", type=int, default=None, help="bind port (default from config: 11434)")
    p.add_argument("--config", default=None, help="explicit config file path")
    p.add_argument("--version", action="version", version=f"duckrun {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cfg = DuckRunConfig.load(explicit_path=args.config, cli=args)
    app = create_app(cfg)
    print(f"[duckrun] v{__version__} serving on http://{cfg.host}:{cfg.port}")
    print(f"[duckrun] data dir: {cfg.data_dir}")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    sys.exit(main())
