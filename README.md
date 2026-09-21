# 🦆 DuckRun

Your own LM Studio-style local AI app: **GUI + model manager + local OpenAI-compatible server**, with pluggable inference backends.

v0.1.0 is the working skeleton — real process management, real Hugging Face downloads, real streaming chat. Built for one person first (Ryan), Apple-Silicon-first, no cloud, no accounts, no telemetry.

## v1 scope (this skeleton)

- **Backends**: `llama-server` binary for GGUF (everywhere), `python -m mlx_lm.server` for MLX (Apple Silicon). Inco Splash lands later as a third backend behind the same interface.
- **Model manager**: download any public Hugging Face repo with live progress, local registry (`~/.duckrun/models.json`), disk-space readout, delete.
- **Local server**: OpenAI-compatible `GET /v1/models` and `POST /v1/chat/completions` (streaming + non-streaming) — point any LM Studio/Ollama-compatible tool at it.
- **Web UI**: single page, no build step — model list, download progress, chat.

## Requirements

- Python 3.10+
- For GGUF models: a `llama-server` binary on PATH (ships with llama.cpp releases) — or set `backends.llama_cpp_binary` in config.
- For MLX models (Apple Silicon Macs): `pip install mlx-lm`
- Neither is needed to run the app itself — the UI, registry, and downloads all work without a backend; loading a model is what needs one.

## Run it

```bash
cd ~/workspace/projects/local-ai-app   # (folder gets renamed to duckrun/ later)
./run.sh                 # first run creates .venv and installs deps
# or: ./run.sh --port 1234 --host 127.0.0.1
```

Then open **http://127.0.0.1:11434** in a browser.

Copy `config.example.yaml` to `duckrun.yaml` (next to `run.sh`) or `~/.duckrun/config.yaml` to tweak host, port, data dir, backend binaries, and extra launch flags. CLI flags beat the config file.

## Try it (no model needed)

```bash
curl localhost:11434/health
curl localhost:11434/v1/models
curl localhost:11434/api/backend/status   # shows which backends this machine can run
```

With a backend installed, download e.g. `mlx-community/Qwen3-4B-4bit` in the UI, hit **Load**, and chat. Anything that speaks OpenAI's API works too:

```bash
curl localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Say hi, duck."}],"stream":true}'
```

## Layout

```
duckrun/            # the app (pip-installable package)
  api/              # FastAPI app: /v1/* (OpenAI-compat) + /api/* (management)
  backends/         # Backend interface + EngineManager (process supervision + proxying)
  models/           # registry + HF downloader
  server/           # ManagedProcess, free-port allocation
  config.py         # YAML config + CLI overrides
web/                # single-page UI (plain HTML/JS, no build)
run.sh              # venv bootstrap + launcher
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and [ROADMAP.md](ROADMAP.md) for what's next.
