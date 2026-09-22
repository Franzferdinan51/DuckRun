# DuckRun roadmap

## v1 — local chat + downloads ✅ (this skeleton)

- [x] FastAPI server: OpenAI-compatible `/v1/models`, `/v1/chat/completions` (streaming)
- [x] Pluggable backends: llama.cpp (GGUF) + MLX (Apple Silicon) behind one interface
- [x] Real process supervision: spawn, health-check, graceful shutdown
- [x] Model manager: HF downloads with progress, registry, disk readout, delete
- [x] Web UI: models view + streaming chat, no build step
- [x] Harden on the Mac mini: installed mlx-lm 0.31.3, verified server flags
      (2026-09-22) — `python -m mlx_lm.server` is deprecated upstream; backend now
      uses `python -m mlx_lm server`; `[mlx]` extra added to pyproject, run.sh
      auto-installs it on darwin/arm64
- [ ] Verify `llama-server` argv against the llama.cpp release Ryan installs
- [x] First real inference run end-to-end (download → load → chat) (2026-09-22) —
      full pipeline verified live on the Mac mini through DuckRun's own code:
      DownloadManager (MLX weight dir, 148 MB, format auto-detected "mlx") →
      registry → EngineManager.load (MLX backend) → engine.chat → 200 with a real
      completion → unload + full cleanup. Test fixture removed; nothing left behind.
- [x] Fixed: EngineManager sent DuckRun's slugified registry id
      ("org--name") as the chat `model` field; mlx_lm.server validates it as an
      HF repo_id and answers 404 + plain-text body. Backends now expose
      `public_model_name()` — MLX sends the real repo_id. Also hardened
      `/v1/chat/completions` against non-JSON backend error bodies.

## v2 — server mode + tool calling

- Local server mode as a first-class feature: `--serve` defaults, LAN bind option,
  API key auth for network exposure (never default-on)
- Tool calling: pass `tools` through to backends that support it (llama-server
  does), function-call UI in chat
- Multi-model: keep N backends warm, route per request (ties into SystemOne's
  tier idea — cheapest sufficient local model)
- Download queue: pause/resume, bandwidth limit, scheduled off-hours downloads
- Model library: curated starter list (small MLX quants that fit 24 GB), one-click
- Chat upgrades: markdown render, stop/regenerate, conversation history on disk

## v3 — native wrapper

- Tauri (preferred: tiny, Rust, uses system webview) or Electron shell around
  the web UI + bundled Python server
- macOS `.app` / `.dmg` build; menu-bar mode ("server runs headless, UI on demand")
- Auto-update channel
- Splash backend (Inco) as third engine — needs 36 GB+ RAM, so this is really
  "when the Mac Studio lands" material

## Non-goals (staying out deliberately)

- Writing our own transformer kernels — the supervisor+proxy design is the product
- Cloud accounts, telemetry, model store, subscriptions
- Windows/Linux native wrappers before the Mac app is solid
