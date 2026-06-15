"use strict";

const $ = (id) => document.getElementById(id);
const STAGE_ORDER = ["story", "voice", "audio", "subtitles", "video", "publish"];
let stageEls = {};
let lastAudio = null;
let lastVideo = null;

// ---- helpers ------------------------------------------------------------- //
function fmtTime(secs) {
  if (secs == null) return "";
  secs = Math.max(0, Math.round(secs));
  const m = Math.floor(secs / 60), s = secs % 60;
  return m ? `${m}m ${s.toString().padStart(2, "0")}s` : `${s}s`;
}

function setBar(fillEl, frac) {
  fillEl.style.width = `${Math.round((frac || 0) * 100)}%`;
}

// ---- one-time render of stage cards -------------------------------------- //
function buildStages(stages) {
  const wrap = $("stages");
  wrap.innerHTML = "";
  stageEls = {};
  stages.forEach((st) => {
    const el = document.createElement("div");
    el.className = "stage";
    el.dataset.id = st.id;
    el.innerHTML = `
      <div class="stage-head">
        <span class="ico"></span>
        <span class="name">${st.label}</span>
        <span class="elapsed"></span>
      </div>
      <div class="bar"><div class="fill"></div></div>
      <div class="msg"></div>`;
    wrap.appendChild(el);
    stageEls[st.id] = el;
  });
}

// ---- main render --------------------------------------------------------- //
function render(state) {
  if (!state || !state.stages) return;
  if (Object.keys(stageEls).length !== state.stages.length) buildStages(state.stages);

  // overall
  setBar($("overall-fill"), state.overall);
  $("overall-pct").textContent = `${Math.round((state.overall || 0) * 100)}%`;
  const running = state.status === "running";
  const live = $("live");
  live.className = "live " + (running ? "run" : "on");
  $("live-state").textContent = running
    ? (state.demo ? "demo running" : "running")
    : (state.status || "idle");

  if (running) {
    const active = state.stages.find((s) => s.status === "running");
    $("overall-label").textContent = active ? active.message || active.label : "Working…";
    $("overall-eta").textContent =
      `elapsed ${fmtTime(state.elapsed)}` + (state.eta != null ? ` · ~${fmtTime(state.eta)} left` : "");
  } else {
    $("overall-label").textContent = state.summary && state.summary.title
      ? `Done — ${state.summary.title}`
      : (state.status === "error" ? "Run ended with an error" : "Idle");
    $("overall-eta").textContent = state.elapsed ? `took ${fmtTime(state.elapsed)}` : "";
  }
  $("btn-stop").disabled = !running;
  $("btn-start").disabled = running;
  $("btn-demo").disabled = running;

  // stages
  const byId = {};
  state.stages.forEach((s) => (byId[s.id] = s));
  state.stages.forEach((st) => {
    const el = stageEls[st.id];
    if (!el) return;
    el.className = "stage " + st.status;
    setBar(el.querySelector(".fill"), st.progress);
    el.querySelector(".msg").textContent = st.error || st.message || "";
    el.querySelector(".elapsed").textContent = st.elapsed != null ? `${st.elapsed}s` : "";
  });

  // script panel
  const story = byId.story || {};
  const text = (story.artifacts && story.artifacts.text) || "";
  const scriptEl = $("script-text");
  if (text) {
    scriptEl.textContent = text;
    scriptEl.classList.toggle("streaming", story.status === "running");
    scriptEl.scrollTop = scriptEl.scrollHeight;
  } else if (story.status === "pending") {
    scriptEl.textContent = "Waiting for the next story…";
    scriptEl.classList.remove("streaming");
  }
  const sm = story.artifacts || {};
  $("story-meta").textContent = sm.title
    ? `${sm.title}${sm.rating ? " · " + sm.rating + "/10" : ""}${sm.subreddit ? " · r/" + sm.subreddit : ""}`
    : "";

  // voice meta
  const voice = byId.voice || {};
  $("voice-meta").textContent = (voice.artifacts && voice.artifacts.engine)
    ? `${voice.artifacts.engine}${voice.artifacts.voice ? " · " + voice.artifacts.voice : ""}` : "";

  // audio player
  const audioUrl = (byId.audio && byId.audio.artifacts && byId.audio.artifacts.audio_url)
    || (voice.artifacts && voice.artifacts.audio_url);
  toggleMedia("audio", "audio-empty", audioUrl, state.demo, (url) => {
    if (url !== lastAudio) { $("audio").src = url; lastAudio = url; }
  });

  // video player
  const video = byId.video || {};
  const videoUrl = video.artifacts && (video.artifacts.video_url || video.artifacts.final_url);
  $("video-meta").textContent = (video.artifacts && video.artifacts.background) || "";
  toggleMedia("video", "video-empty", videoUrl, state.demo, (url) => {
    if (url !== lastVideo) { $("video").src = url; lastVideo = url; }
  });

  // live chat preview
  const chat = (video.artifacts && video.artifacts.chat) || [];
  const chatEl = $("chat-preview");
  if (chat.length) {
    $("chat-meta").textContent = `${chat.length} reactions`;
    chatEl.innerHTML = chat.map((line) => {
      const idx = line.indexOf(":");
      const user = idx > 0 ? line.slice(0, idx) : "chat";
      const msg = idx > 0 ? line.slice(idx + 1) : line;
      return `<div class="cl"><span class="u">${escapeHtml(user)}</span>${escapeHtml(msg)}</div>`;
    }).join("");
  } else {
    $("chat-meta").textContent = "";
    chatEl.innerHTML = `<div class="empty">No chat yet</div>`;
  }

  // logs
  const logs = state.logs || [];
  $("logs").innerHTML = logs.slice(-120).map((l) => {
    const t = new Date(l.t * 1000).toLocaleTimeString();
    return `<div class="ln ${l.level}"><span class="t">${t}</span>${escapeHtml(l.msg)}</div>`;
  }).join("");
  $("logs").scrollTop = $("logs").scrollHeight;
}

function toggleMedia(elId, emptyId, url, demo, apply) {
  const el = $(elId), empty = $(emptyId);
  if (url && !demo) {
    el.style.display = "block"; empty.style.display = "none"; apply(url);
  } else {
    el.style.display = "none";
    empty.style.display = "block";
    empty.textContent = demo ? "Preview disabled in demo mode" : `No ${elId} yet`;
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// ---- readiness ----------------------------------------------------------- //
async function loadReadiness() {
  try {
    const r = await (await fetch("/api/readiness")).json();
    if (r.persona) {
      document.documentElement.style.setProperty("--accent", r.persona.accent || "#FF2E63");
      $("tagline").textContent = r.persona.tagline || "";
    }
    const wrap = $("readiness");
    wrap.innerHTML = "";
    Object.values(r.checks).forEach((c) => {
      const chip = document.createElement("span");
      chip.className = "chip " + (c.ok ? "ok" : "bad") + (c.optional ? " opt" : "");
      chip.innerHTML = `<b>${c.label}</b>${c.ok ? "" : " — " + c.hint}`;
      wrap.appendChild(chip);
    });
    const startBtn = $("btn-start");
    if (!r.can_run_real) {
      startBtn.title = "Missing required setup — try Demo, or fill in your .env";
    } else {
      startBtn.title = "";
    }
  } catch (e) { /* ignore */ }
}

// ---- websocket ----------------------------------------------------------- //
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => { $("live").className = "live on"; $("live-state").textContent = "connected"; };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") render(msg.state);
  };
  ws.onclose = () => {
    $("live").className = "live"; $("live-state").textContent = "reconnecting…";
    setTimeout(connect, 1500);
  };
  ws.onerror = () => ws.close();
}

// ---- controls ------------------------------------------------------------ //
async function post(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

$("btn-start").onclick = async () => {
  const res = await post("/api/run", { count: parseInt($("count").value || "1", 10) });
  if (!res.ok) alert(res.error || "Could not start");
};
$("btn-demo").onclick = () => post("/api/run", { demo: true });
$("btn-stop").onclick = () => post("/api/stop", {});

// ---- tabs + sources management ------------------------------------------- //
const LINK_UI = {
  background: { input: "bg-input", list: "bg-list", meta: "bg-meta", hint: "bg-hint", env: "BG" },
  music: { input: "mus-input", list: "mus-list", meta: "mus-meta", hint: "mus-hint", env: "MUSIC" },
};

function switchView(view) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view === "sources") { loadLinks("background"); loadLinks("music"); loadVoices(); }
}

async function loadVoices() {
  try {
    const data = await (await fetch("/api/voices")).json();
    $("voice-cur").textContent = data.current ? `current: ${data.current}` : "";
    const sel = $("voice-select");
    sel.innerHTML = `<option value="">— ${data.voices.length ? "pick a voice" : "your ElevenLabs voices"} —</option>` +
      data.voices.map((v) => `<option value="${v.voice_id}"${v.voice_id === data.current ? " selected" : ""}>${escapeHtml(v.name)} — ${v.voice_id}</option>`).join("");
    $("voice-hint").innerHTML = data.has_key
      ? (data.voices.length ? "Pick one of your voices, or paste any Voice ID." : "Couldn't list voices — paste a Voice ID, or check your ElevenLabs key.")
      : "Add your ElevenLabs key (run setup) to list voices. You can still paste a Voice ID.";
  } catch (e) { /* ignore */ }
}

async function saveVoice() {
  const vid = ($("voice-id").value.trim() || $("voice-select").value).trim();
  if (!vid) { alert("Pick a voice or paste a Voice ID."); return; }
  const res = await post("/api/voice", { voice_id: vid });
  if (res.ok) { $("voice-id").value = ""; loadVoices(); }
  else alert(res.error || "Could not save voice");
}
$("voice-save").onclick = saveVoice;
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => switchView(t.dataset.view)));

async function loadLinks(kind) {
  try {
    renderLinks(kind, await (await fetch(`/api/links/${kind}`)).json());
  } catch (e) { /* ignore */ }
}

function renderLinks(kind, data) {
  const ui = LINK_UI[kind];
  const links = data.links || [];
  $(ui.meta).textContent = `${links.length} link${links.length === 1 ? "" : "s"} · source: ${data.source}`;
  const hint = $(ui.hint);
  if (!data.ytdlp) {
    hint.innerHTML = "⚠ yt-dlp isn't installed (needed for YouTube links). " +
      `<button class="btn small install-ytdlp">Install yt-dlp</button>`;
    hint.className = "hint warn";
    hint.querySelector(".install-ytdlp").onclick = (e) => installYtdlp(e.target);
  } else if (data.source === "local" && links.length) {
    hint.innerHTML = `Source is <b>local</b>. Set <code>K100DRA_${ui.env}_SOURCE=auto</code> in .env to use these.`;
    hint.className = "hint warn";
  } else {
    hint.textContent = links.length ? "Used automatically, rotating through your links." : "No links yet — paste some above.";
    hint.className = "hint";
  }
  $(ui.list).innerHTML = links.length
    ? links.map((url) =>
        `<li><span class="url" title="${escapeHtml(url)}">${escapeHtml(url)}</span>` +
        `<button class="rm" data-kind="${kind}" data-url="${escapeHtml(url)}">✕</button></li>`).join("")
    : `<li class="muted">empty</li>`;
  $(ui.list).querySelectorAll(".rm").forEach((b) => (b.onclick = () => removeLink(b.dataset.kind, b.dataset.url)));
}

async function addLinks(kind) {
  const ui = LINK_UI[kind];
  const text = $(ui.input).value.trim();
  if (!text) return;
  renderLinks(kind, await post(`/api/links/${kind}`, { add: text }));
  $(ui.input).value = "";
}

async function removeLink(kind, url) {
  renderLinks(kind, await post(`/api/links/${kind}`, { remove: url }));
}

async function installYtdlp(btn) {
  btn.disabled = true;
  btn.textContent = "Installing… (~20s)";
  try {
    const res = await post("/api/install/ytdlp", {});
    if (res.ok) {
      loadLinks("background"); loadLinks("music");
    } else {
      alert("Install failed:\n" + (res.message || "unknown error"));
      btn.disabled = false; btn.textContent = "Install yt-dlp";
    }
  } catch (e) {
    alert("Install failed: " + e);
    btn.disabled = false; btn.textContent = "Install yt-dlp";
  }
}

$("bg-add").onclick = () => addLinks("background");
$("mus-add").onclick = () => addLinks("music");

loadReadiness();
connect();
setInterval(loadReadiness, 8000);
