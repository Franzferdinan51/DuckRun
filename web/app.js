/* DuckRun web UI — plain JS, talks to the local DuckRun API. No build step. */
const $ = (id) => document.getElementById(id);
const fmtGB = (b) => (b / 1e9).toFixed(1) + " GB";

async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}

/* ---------- nav ---------- */
document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
    $("view-" + btn.dataset.view).classList.remove("hidden");
    if (btn.dataset.view === "chat") refreshChatModels();
  });
});

/* ---------- engine status pill ---------- */
async function refreshStatus() {
  try {
    const s = await api("GET", "/api/backend/status");
    const pill = $("engine-pill");
    if (s.loaded_model) {
      pill.textContent = `● ${s.loaded_model} (${s.backend})`;
      pill.className = "pill live";
    } else {
      pill.textContent = "no model loaded";
      pill.className = "pill idle";
    }
  } catch (_) {}
}

/* ---------- models ---------- */
async function refreshModels() {
  const { models, free_bytes } = await api("GET", "/api/models");
  const status = await api("GET", "/api/backend/status").catch(() => ({}));
  $("disk-free").textContent = `· ${fmtGB(free_bytes)} free`;
  const list = $("model-list");
  list.innerHTML = "";
  if (!models.length) {
    list.innerHTML = '<p class="muted">No models yet — download one above.</p>';
  }
  for (const m of models) {
    const card = document.createElement("div");
    card.className = "model-card";
    const loaded = status.loaded_model === m.id;
    card.innerHTML = `
      <h3>${m.id}${loaded ? '<span class="loaded-badge">● loaded</span>' : ""}</h3>
      <div><span class="fmt fmt-${m.format}">${m.format.toUpperCase()}</span></div>
      <div class="meta">${m.repo_id}<br>${fmtGB(m.size_bytes)} · ${m.downloaded_at || ""}</div>
      <div class="btnrow">
        ${loaded
          ? `<button data-act="unload">Unload</button>`
          : `<button data-act="load" class="primary">Load</button>`}
        <button data-act="del" class="danger">Delete</button>
      </div>`;
    card.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => modelAction(b.dataset.act, m.id))
    );
    list.appendChild(card);
  }
}

async function modelAction(act, id) {
  try {
    if (act === "load") await api("POST", "/api/backend/load", { model_id: id });
    if (act === "unload") await api("POST", "/api/backend/unload");
    if (act === "del" && confirm(`Delete ${id} and its files?`))
      await api("DELETE", "/api/models/" + encodeURIComponent(id));
  } catch (e) { alert("DuckRun: " + e.message); }
  refreshModels(); refreshStatus();
}

/* ---------- downloads ---------- */
$("dl-btn").addEventListener("click", async () => {
  const repo = $("dl-repo").value.trim();
  $("dl-error").classList.add("hidden");
  if (!repo || !repo.includes("/")) {
    $("dl-error").textContent = "Enter a Hugging Face repo like owner/model.";
    $("dl-error").classList.remove("hidden");
    return;
  }
  try {
    await api("POST", "/api/models/download", { repo_id: repo, format: $("dl-format").value });
    $("dl-repo").value = "";
  } catch (e) {
    $("dl-error").textContent = "DuckRun: " + e.message;
    $("dl-error").classList.remove("hidden");
  }
});

async function refreshJobs() {
  const { jobs } = await api("GET", "/api/downloads").catch(() => ({ jobs: [] }));
  const box = $("jobs");
  box.innerHTML = "";
  let active = false;
  for (const j of jobs.slice().reverse()) {
    if (j.state === "downloading" || j.state === "queued") active = true;
    const pct = (j.progress * 100).toFixed(1);
    const el = document.createElement("div");
    el.className = "job" + (j.state === "error" ? " err" : "");
    el.innerHTML = `
      <div><strong>${j.repo_id}</strong> — ${j.state}${j.state === "error" ? ": " + j.error : ""}</div>
      ${j.state === "downloading" ? `
        <div class="bar"><div style="width:${pct}%"></div></div>
        <div class="muted">${pct}% · ${fmtGB(j.done_bytes)} / ${fmtGB(j.total_bytes)} · ${j.current_file}</div>` : ""}
      ${j.state === "done" ? `<div class="muted">done — model registered, ready to load</div>` : ""}`;
    box.appendChild(el);
  }
  if (active || jobs.some((j) => j.state === "done")) refreshModels();
}

/* ---------- chat ---------- */
let chatHistory = [];

async function refreshChatModels() {
  const { data } = await api("GET", "/v1/models");
  const sel = $("chat-model");
  const prev = sel.value;
  sel.innerHTML = "";
  for (const m of data) {
    const o = document.createElement("option");
    o.value = m.id;
    o.textContent = m.id + (m.loaded ? "  ● loaded" : "");
    sel.appendChild(o);
  }
  const status = await api("GET", "/api/backend/status").catch(() => ({}));
  if (status.loaded_model) sel.value = status.loaded_model;
  else if (prev) sel.value = prev;
  $("chat-hint").textContent = status.loaded_model
    ? `loaded: ${status.loaded_model}`
    : "pick a model and hit Load — the backend spawns automatically";
}

$("chat-load").addEventListener("click", async () => {
  const id = $("chat-model").value;
  if (!id) return;
  try {
    await api("POST", "/api/backend/load", { model_id: id });
  } catch (e) { alert("DuckRun: " + e.message); }
  refreshChatModels(); refreshStatus();
});

$("chat-unload").addEventListener("click", async () => {
  await api("POST", "/api/backend/unload").catch((e) => alert("DuckRun: " + e.message));
  refreshChatModels(); refreshStatus();
});

function addMsg(role, text) {
  const el = document.createElement("div");
  el.className = "msg " + role;
  el.innerHTML = `<span class="role">${role === "user" ? "you" : "🦆 duckrun"}</span><span class="body"></span>`;
  el.querySelector(".body").textContent = text;
  $("messages").appendChild(el);
  $("messages").scrollTop = $("messages").scrollHeight;
  return el;
}

async function sendChat() {
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  $("chat-send").disabled = true;
  addMsg("user", text);
  chatHistory.push({ role: "user", content: text });
  const shell = addMsg("assistant", "");
  shell.classList.add("thinking");
  const bodyEl = shell.querySelector(".body");
  try {
    const r = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory, stream: true }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || r.statusText);
    }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "", out = "";
    shell.classList.remove("thinking");
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const p of parts) {
        const line = p.trim().split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") continue;
        try {
          const delta = JSON.parse(payload).choices?.[0]?.delta?.content || "";
          out += delta;
          bodyEl.textContent = out;
          $("messages").scrollTop = $("messages").scrollHeight;
        } catch (_) {}
      }
    }
    chatHistory.push({ role: "assistant", content: out });
  } catch (e) {
    shell.classList.remove("thinking");
    bodyEl.textContent = "DuckRun error: " + e.message;
  }
  $("chat-send").disabled = false;
}

$("chat-send").addEventListener("click", sendChat);
$("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

/* ---------- boot + polling ---------- */
refreshStatus(); refreshModels(); refreshJobs(); refreshChatModels();
setInterval(refreshJobs, 2000);
setInterval(refreshStatus, 5000);
