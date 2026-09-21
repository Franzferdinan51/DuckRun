# DuckRun roadmap

## v1 — local chat + downloads ✅ (this skeleton)

- [x] FastAPI server: OpenAI-compatible `/v1/models`, `/v1/chat/completions` (streaming)
- [x] Pluggable backends: llama.cpp (GGUF) + MLX (Apple Silicon) behind one interface
- [x] Real process supervision: spawn, health-check, graceful shutdown
- [x] Model manager: HF downloads with progress, registry, disk readout, delete
- [x] Web UI: models view + streaming chat, no build step
- [ ] Harden on the Mac mini: verify `mlx_lm.server` flags against installed mlx-lm version
- [ ] Verify `llama-server` argv against the llama.cpp release Ryan installs
- [ ] First real inference run end-to-end (download → load → chat)

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
