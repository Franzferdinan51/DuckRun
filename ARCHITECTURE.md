# DuckRun architecture (v0.1.0)

## The one big decision

DuckRun does **not** do inference itself. Every supported engine already ships
an OpenAI-compatible HTTP server (`llama-server`, `mlx_lm.server`, and later
Inco's Splash). So DuckRun is a **supervisor + proxy + model manager**:

```
┌─────────────┐      ┌──────────────────────────────────────┐
│   web UI    │─────▶│            DuckRun (FastAPI)          │
│ (or any     │      │                                      │
│  OpenAI     │      │  /v1/* ──▶ EngineManager ──▶ child   │
│  client)    │      │  /api/* ─▶ Registry / Downloader     │
└─────────────┘      └──────────────────────────────────────┘
                                         │ spawn / supervise / proxy
                                         ▼
                              ┌─────────────────────┐
                              │ llama-server :PORT  │  (GGUF)
                              │  — or —             │
                              │ mlx_lm.server :PORT │  (MLX, Apple Silicon)
                              └─────────────────────┘
```

This keeps the Backend interface small and honest: DuckRun manages *processes*,
not tensors.

## Backend interface

`duckrun/backends/base.py` — every engine implements:

```python
class Backend(ABC):
    name: str

    def detect(self) -> BackendInfo:
        """Usable on this machine right now? (binary on PATH, platform OK)"""

    def build_command(self, model_path, port, extra_args) -> list[str]:
        """argv to launch the child server for a model"""

    def health_url(self, port) -> str:
        """URL that stops 5xx-ing once the child is ready"""

    def probe_loaded_model(self, port) -> str | None:
        """Which model id the child reports (best effort)"""
```

`BackendInfo { name, available, reason, formats }` — `reason` is the human
string the UI shows when a backend can't run ("llama-server not found on PATH",
"MLX needs Apple Silicon macOS"). `detect()` never raises; unavailability is data.

### Current implementations

| Backend    | Class            | Child command                              | Health probe   | Formats |
|------------|------------------|--------------------------------------------|----------------|---------|
| `llamacpp` | `LlamaCppBackend`| `llama-server -m <gguf> --port P [...]`    | `GET /health`  | `gguf`  |
| `mlx`      | `MlxBackend`     | `python -m mlx_lm.server --model <dir> --port P [...]` | `GET /v1/models` | `mlx` |

MLX has no `/health` endpoint, so readiness is "GET /v1/models stops 5xx-ing".
Both children are OpenAI-compatible, so chat traffic is proxied verbatim.

### EngineManager (`backends/manager.py`)

Owns exactly one loaded model at a time (v1; matches LM Studio's default):

- `load(model_id, path, format)` → picks backend by format → `find_free_port()`
  → builds argv (config `*_extra_args` appended) → `ManagedProcess.start()`
  (raises on boot failure; nothing half-loaded) → records active backend/port.
- `unload()` → SIGTERM, 10s grace, SIGKILL.
- `chat(body)` / `chat_stream(body)` → httpx passthrough to
  `127.0.0.1:<port>/v1/chat/completions`, injecting `model` when absent.
  Streaming uses `httpx.AsyncClient.stream` and yields raw SSE bytes untouched.
- `status()` → loaded model + per-backend availability for the UI.

### ManagedProcess (`server/process.py`)

`subprocess.Popen` wrapper: tails child stdout/stderr into DuckRun's logs
(`[duckrun:llamacpp:…]` prefix), polls the health URL until `startup_timeout`
(config, default 120s), kills the child if boot times out. `stop()` is
terminate → wait → kill. Daemon tail thread; nothing leaks on unload.

### Adding Splash later

New file `backends/splash.py` implementing the four methods (child command is
whatever Inco's Splash server uses; health probe TBD), one line in the manager's
backend dict, `"splash": "splash"` in `FORMAT_BACKENDS`. No other code changes.
The 36 GB RAM requirement is a *model* constraint, not an interface one —
`detect()` can encode it ("needs ≥36 GB unified memory, this Mac has 24").

## Model manager

- **Registry** (`models/registry.py`): `~/.duckrun/models.json` + `models/` dir.
  Entries carry `id` (repo slug), `repo_id`, `format`, `path`, `size_bytes`,
  `downloaded_at`. `free_bytes()` feeds the UI's disk readout.
- **Downloader** (`models/downloader.py`): worker thread per download using
  `huggingface_hub` (`model_info` for the file list, `hf_hub_download` per file,
  symlinks off). Progress = bytes done / bytes total, polled by the UI via
  `GET /api/downloads`. Format filter: `gguf` keeps only `*.gguf`, `mlx` drops
  them, `auto` keeps everything and detects from the file list. No tokens, no
  secrets — public repos only in v1 (set `HF_TOKEN` in your own env for gated
  ones; DuckRun never asks for it).

## API layer

`duckrun/api/app.py` wires it together; lifespan hook unloads the model on
shutdown so no child outlives the server. Routes:

- **OpenAI-compatible**: `GET /v1/models` (registry → OpenAI shape, plus
  `loaded`/`format` extras), `POST /v1/chat/completions` (stream ⇄
  `StreamingResponse(text/event-stream)`, else JSON passthrough).
- **Management**: `/health`, `/api/models`, `/api/models/download`,
  `/api/downloads`, `/api/backend/status|load|unload`.
- **UI**: `web/` mounted at `/` last so `/v1/*` and `/api/*` always win.

## Config

`config.py`: `duckrun.yaml` (cwd or package dir) → `~/.duckrun/config.yaml` →
defaults; CLI `--host/--port` wins. YAML via PyYAML, JSON fallback. Data dir
defaults to `~/.duckrun`; `~` expanded; created on boot. No macOS-only paths —
`Path.home()` everywhere.
