// Entry point (docs/thiet-ke-giao-dien.md). One screen, two modes:
//   simple  pick a vehicle that has someone behind it, choose how it brakes, see what happens, download
//   tech    the same, plus exact parameters, overlays, timeline events and the dock (dock.js)
// Every scenario the user makes goes through /api/simulate (fast, no esmini); "Tải" goes through
// /api/export (esmini replays it first). Drawing is in viewer.js / viewer3d.js.

import {
  exportEvent, getStatus, listJobs, listScenes, listSources, loadScene, processScenes, rareUrl, removeSource,
  simulateEvent,
} from "./api.js";
import { deviationAt, deviationSeries, drawDeviationChart } from "./deviation.js";
import { renderDock } from "./dock.js";
import { GROUPS, KIND_LABEL, escapeHtml, metres, num, seconds } from "./format.js";
import { helpIcon, initHelp } from "./help.js";
import { initSourceDialog } from "./sources-dialog.js";
import { Timeline } from "./timeline.js";
import { Viewer } from "./viewer.js";
import { Viewer3D } from "./viewer3d.js";

const $ = (id) => document.getElementById(id);
const DEFAULTS = { decel: 4, target: "stop", dwell: 0, react: true, reaction: 1.0 };
const JOB_POLL_MS = 1000;
const state = {
  mode: "simple", sources: [], source: null, scenes: [], scene: null, jobs: [],
  actor: null, params: { ...DEFAULTS, t0: 0 }, sim: null, exported: null, sensitivity: null,
  overlays: { ghosts: true, leaders: true, gap: true, labels: false, path: false, stoplines: true, baseline: false },
  dock: "chart", selected: null, request: 0,
};

function toast(text, isError = false, ms = 3500) {
  const box = $("status");
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.hidden = !text;
  clearTimeout(toast.timer);
  if (text && ms) toast.timer = setTimeout(() => { box.hidden = true; }, ms);
}

// ---------------------------------------------------------------- viewers and timeline
const views = {
  top: new Viewer($("viewer"), { onSelect: (track) => onObjectClick(track) }),
  free: new Viewer3D($("viewer3d"), { onSelect: (track) => onObjectClick(track) }),
};
const eachView = (fn) => Object.values(views).forEach(fn);

const timeline = new Timeline(
  { play: $("play"), slider: $("time"), label: $("time-label"), speed: $("speed") },
  (t) => onTime(t),
);
$("step-back").addEventListener("click", () => timeline.setTime(timeline.time - 0.05));
$("step-fwd").addEventListener("click", () => timeline.setTime(timeline.time + 0.05));
$("follow").addEventListener("change", (e) => eachView((v) => v.setFollow(e.target.checked)));

for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => {
    const view = button.dataset.view;
    $("viewer").hidden = view !== "top";
    $("viewer3d").hidden = view !== "free";
    for (const b of document.querySelectorAll("[data-view]")) b.classList.toggle("on", b === button);
    if (view === "top") views.top.draw(); else views.free.resize();
  });
}

function onTime(t) {
  eachView((v) => v.setTime(t));
  if (state.actor && !state.sim && state.mode === "simple") setT0(nearestStart(state.actor, t));
  views.top.setOverlay(overlayAt(t));
  drawMarkers();
  if (state.mode === "tech") { renderDeviation(); renderDock(dockContext(), true); }
}

// ---------------------------------------------------------------- mode
for (const button of document.querySelectorAll("[data-mode]")) {
  button.addEventListener("click", () => setMode(button.dataset.mode));
}

function setMode(mode) {
  state.mode = mode;
  document.body.classList.toggle("mode-tech", mode === "tech");
  document.body.classList.toggle("mode-simple", mode === "simple");
  for (const b of document.querySelectorAll("[data-mode]")) b.classList.toggle("on", b.dataset.mode === mode);
  applyLayers();
  renderAll();
  requestAnimationFrame(() => { views.top.requestDraw(); drawMarkers(); });
}

// Overlay chips (technical mode).
for (const chip of document.querySelectorAll("[data-overlay]")) {
  chip.addEventListener("click", () => {
    const key = chip.dataset.overlay;
    if (key === "measure") {
      const on = !chip.classList.contains("on");
      chip.classList.toggle("on", on);
      views.top.setMeasuring(on);
      return;
    }
    state.overlays[key] = !state.overlays[key];
    chip.classList.toggle("on", state.overlays[key]);
    applyLayers();
    views.top.setOverlay(overlayAt(timeline.time));
  });
}

function applyLayers() {
  const tech = state.mode === "tech";
  eachView((v) => {
    v.setLayer("gt", false);
    v.setLayer("labels", tech && state.overlays.labels);
    v.setLayer("ghosts", !tech || state.overlays.ghosts);
    v.setLayer("stoplines", !tech || state.overlays.stoplines);
    v.setLayer("baseline", tech && state.overlays.baseline && !state.sim);
  });
}

const getCss = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const trackByName = (name) => state.scene?.tracks.find((t) => t.name === name) || null;

function indexAt(times, t) {
  let lo = 0, hi = times.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; (times[mid] <= t ? (lo = mid) : (hi = mid)); }
  return Math.abs(times[hi] - t) < Math.abs(times[lo] - t) ? hi : lo;
}

// What the top-down viewer draws on top of the objects at time t.
function overlayAt(t) {
  const tech = state.mode === "tech";
  const overlay = { pick: [], arrows: [], tags: [], path: null };
  const scene = state.scene;
  if (!scene) return overlay;
  if (!state.sim) overlay.pick = Object.keys(scene.selectable || {}).filter((name) => name !== state.actor);
  const sim = state.sim;
  if (sim) {
    const i = indexAt(sim.t, t);
    if (tech && state.overlays.leaders) {
      for (const [name, info] of Object.entries(sim.changed)) {
        const seg = info.leaders.find(([a, b]) => t >= a - 1e-6 && t <= b + 0.05);
        if (seg) overlay.arrows.push([name, seg[2]]);
      }
    }
    const ego = sim.series.ego;
    if (!tech || state.overlays.gap) {
      const gap = ego?.gap?.[i], ttc = ego?.ttc?.[i];
      if (gap != null) {
        overlay.tags.push({ name: "ego", colour: gap < 2 ? getCss("--danger") : getCss("--obj-gt"),
          text: `cách xe trước ${num(gap, 1)} m${ttc != null && ttc < 10 ? ` · TTC ${num(ttc, 1)} s` : ""}` });
      }
    }
    if (tech) {
      for (const [name, s] of Object.entries(sim.series)) {
        if (name === "ego" || s.v[i] == null) continue;
        overlay.tags.push({ name, text: `${num(s.v[i] * 3.6, 0)} km/h` });
      }
    }
  }
  if (tech && state.overlays.path && state.actor) {
    const poses = state.sim?.changed[state.actor]?.poses || trackByName(state.actor)?.pilot;
    if (poses) overlay.path = poses.x.map((x, k) => [x, poses.y[k]]);
  }
  return overlay;
}

// ---------------------------------------------------------------- timeline markers
const MARKER = {
  brake_start: ["phanh", "--obj-actor"], target_reached: ["dừng / chậm xong", "--obj-actor"],
  dwell_end: ["đi tiếp", "--obj-actor"], reacts: ["phản ứng", "--obj-reacted"], closest: ["gần nhất", "--danger"],
  collision: ["va chạm", "--danger"],
};

function drawMarkers() {
  const canvas = $("markers");
  const { width, height } = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const duration = state.scene?.duration;
  if (!duration || !width) return;
  const X = (t) => 8 + (t / duration) * (width - 16);  // the range input's thumb inset
  if (state.mode === "tech") {
    ctx.fillStyle = getCss("--warn-bg");
    for (const spans of Object.values(state.scene.label_problems || {})) {
      for (const [a, b] of spans) ctx.fillRect(X(a) - 2, 0, Math.max(4, X(b) - X(a)), height);
    }
  }
  const marks = state.sim ? state.sim.markers : state.actor ? [{ t: state.params.t0, kind: "brake_start" }] : [];
  ctx.font = "10px Segoe UI, sans-serif";
  for (const m of marks) {
    if (state.mode === "simple" && !["brake_start", "closest", "collision"].includes(m.kind)) continue;
    const [label, colour] = MARKER[m.kind] || [m.kind, "--muted"];
    ctx.fillStyle = getCss(colour);
    const x = X(m.t);
    ctx.beginPath(); ctx.moveTo(x - 4, 1); ctx.lineTo(x + 4, 1); ctx.lineTo(x, 8); ctx.closePath(); ctx.fill();
    if (["brake_start", "closest", "collision"].includes(m.kind)) ctx.fillText(label, x + 5, 11);
  }
}
$("markers").addEventListener("click", (e) => {
  const duration = state.scene?.duration;
  if (!duration) return;
  const width = $("markers").getBoundingClientRect().width;
  timeline.setTime(((e.offsetX - 8) / (width - 16)) * duration);
});

// ---------------------------------------------------------------- data sources and scenes
const sourceDialog = initSourceDialog({ onAdded: (entry) => loadSources(entry.id) });
$("add-source").addEventListener("click", () => sourceDialog.open());
$("open-data").addEventListener("click", () => { $("data-dialog").hidden = false; renderSceneList(); });
$("close-data").addEventListener("click", () => { $("data-dialog").hidden = true; });
$("data-dialog").addEventListener("click", (e) => { if (e.target === $("data-dialog")) $("data-dialog").hidden = true; });
$("source").addEventListener("change", (e) => openSource(e.target.value));
$("data-source").addEventListener("change", (e) => openSource(e.target.value));
$("scene").addEventListener("change", (e) => openScene(e.target.value));
$("remove-source").addEventListener("click", async () => {
  const source = state.sources.find((s) => s.id === state.source);
  if (!source || !confirm(`Bỏ “${source.label}” khỏi danh sách nguồn?\nDữ liệu và kết quả trên máy vẫn được giữ.`)) return;
  try { await removeSource(source.id); state.source = null; await loadSources(); } catch (error) { toast(error.message, true); }
});
$("process-all").addEventListener("click", () => startProcessing(null));

async function loadSources(selectId = null) {
  state.sources = await listSources();
  for (const select of [$("source"), $("data-source")]) {
    select.innerHTML = state.sources.map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.label)}`
      + `${s.error ? " (lỗi)" : ` (${s.scenes} cảnh)`}</option>`).join("");
  }
  const chosen = selectId || state.source || state.sources[0]?.id;
  if (chosen) await openSource(chosen);
  else toast("Chưa có nguồn dữ liệu. Bấm “Dữ liệu…” để thêm file CSV hoặc thư mục nuScenes.", false, 0);
}

async function openSource(id) {
  state.source = id;
  $("source").value = id; $("data-source").value = id;
  const source = state.sources.find((s) => s.id === id);
  if (source?.error) { state.scenes = []; renderSceneSelect(); renderSceneList(); toast(source.error, true, 0); return; }
  state.scenes = await listScenes(id);
  renderSceneSelect();
  renderSceneList();
  const first = state.scenes.find((s) => s.processed) || state.scenes[0];
  if (first) await openScene(first.name);
}

function renderSceneSelect() {
  $("scene").innerHTML = state.scenes.map((s) => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}`
    + `${s.location ? ` · ${escapeHtml(s.location)}` : ""}</option>`).join("");
  if (state.scene) $("scene").value = state.scene.name;
}

const jobFor = (scene) => [...state.jobs].reverse().find((j) => j.source === state.source && j.scene === scene) || null;

function renderSceneList() {
  const list = $("scene-list");
  list.innerHTML = "";
  for (const scene of state.scenes) {
    const job = jobFor(scene.name);
    const busy = job && (job.status === "queued" || job.status === "running");
    let sub;
    if (busy) sub = `${job.status === "queued" ? "đang chờ" : escapeHtml(job.message)} · ${Math.round(100 * job.progress)}%`;
    else if (job?.status === "failed") sub = `<span class="failed">lỗi: ${escapeHtml(job.error)}</span>`;
    else if (scene.processed) sub = `đã xử lý · ${scene.valid}/${scene.written} cách phanh dùng được · ${scene.rare} ca hiếm`;
    else sub = "chưa xử lý";
    const item = document.createElement("li");
    item.innerHTML = `<div><b>${escapeHtml(scene.name)}</b><div class="desc" title="${escapeHtml(scene.description)}">${escapeHtml(scene.description)}</div></div>`
      + `<div class="state">${sub}${busy ? `<div class="bar"><span style="width:${Math.round(100 * job.progress)}%"></span></div>` : ""}</div>`
      + `<div class="row"><button class="small open">Mở</button>${!busy ? `<button class="small process">${scene.processed ? "Xử lý lại" : "Xử lý"}</button>` : ""}</div>`;
    item.querySelector(".open").addEventListener("click", () => { $("data-dialog").hidden = true; openScene(scene.name); });
    item.querySelector(".process")?.addEventListener("click", () => startProcessing([scene.name]));
    list.append(item);
  }
  const pending = state.scenes.filter((s) => !s.processed).length;
  $("process-all").disabled = pending === 0;
  $("process-all").textContent = pending ? `Xử lý ${pending} cảnh chưa xử lý` : "Đã xử lý hết";
}

async function startProcessing(scenes) {
  try { await processScenes(state.source, scenes); await pollJobs(); } catch (error) { toast(error.message, true); }
}

let polling = null;
async function pollJobs() {
  const before = new Map(state.jobs.map((j) => [j.id, j.status]));
  state.jobs = await listJobs();
  const finished = state.jobs.filter((j) => (j.status === "done" || j.status === "failed") && before.has(j.id) && before.get(j.id) !== j.status);
  const active = state.jobs.filter((j) => j.status === "queued" || j.status === "running");
  if (finished.some((j) => j.source === state.source)) {
    state.scenes = await listScenes(state.source);
    if (finished.some((j) => j.scene === state.scene?.name && j.status === "done")) await openScene(state.scene.name);
  }
  renderSceneList();
  if (active.length) toast(`Đang xử lý ${active.length} cảnh… (xem tiến độ trong “Dữ liệu…”)`, false, 0);
  else if (finished.length) toast("Xử lý xong.");
  clearTimeout(polling);
  if (active.length) polling = setTimeout(pollJobs, JOB_POLL_MS);
}

// ---------------------------------------------------------------- open a scene
async function openScene(name) {
  const request = ++state.request;
  toast(`Đang tải ${name}…`, false, 0);
  try {
    const scene = await loadScene(state.source, name);
    if (request !== state.request) return;
    state.scene = scene;
    $("scene").value = name;
    resetScenario();
    eachView((v) => v.setScene(baseScene()));
    views.top.fit(focusBounds());
    timeline.setDuration(scene.duration);
    applyLayers();
    renderAll();
    toast("");
  } catch (error) {
    if (request === state.request) toast(`Không tải được ${name}: ${error.message}`, true, 0);
  }
}

// Frame the ego's drive and the vehicles that can be made to brake, not the whole map of labels.
function focusBounds() {
  const names = new Set(["ego", ...Object.keys(state.scene.selectable || {})]);
  let [xmin, ymin, xmax, ymax] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const t of state.scene.tracks) {
    if (!names.has(t.name)) continue;
    for (let i = 0; i < t.gt.x.length; i++) {
      xmin = Math.min(xmin, t.gt.x[i]); xmax = Math.max(xmax, t.gt.x[i]);
      ymin = Math.min(ymin, t.gt.y[i]); ymax = Math.max(ymax, t.gt.y[i]);
    }
  }
  const margin = 15;
  return Number.isFinite(xmin) ? [xmin - margin, ymin - margin, xmax + margin, ymax + margin] : null;
}

// The scene as recorded: everyone on the reconstruction the simulation starts from (the ego: its recording).
function baseScene() {
  const tracks = state.scene.tracks.map((t) => ({ ...t, pilot: t.name === "ego" ? t.gt : t.pilot }));
  return { ...state.scene, tracks };
}

function resetScenario() {
  state.actor = null;
  state.sim = null;
  state.exported = null;
  state.sensitivity = null;
  state.selected = null;
  state.params = { ...DEFAULTS, t0: 0 };
}

// ---------------------------------------------------------------- choosing a vehicle and parameters
function onObjectClick(track) {
  const name = track?.name || null;
  state.selected = name;
  eachView((v) => v.setSelected(name));
  if (name && state.scene?.selectable?.[name] && name !== state.actor) chooseActor(name);
  else renderDetails();
}

function chooseActor(name) {
  clearSimulation();
  state.actor = name;
  state.selected = name;
  const info = state.scene.selectable[name];
  state.params = { ...state.params, t0: nearestStart(name, timeline.time), decel: Math.min(state.params.decel, info.max_decel) };
  eachView((v) => v.setSelected(name));
  renderAll();
}

function nearestStart(name, t) {
  const times = state.scene?.selectable?.[name]?.times || [t];
  return times.reduce((best, x) => (Math.abs(x - t) < Math.abs(best - t) ? x : best), times[0]);
}

function setT0(t0) {
  if (state.params.t0 === t0) return;
  state.params.t0 = t0;
  $("t0-simple").textContent = `${num(t0, 1)} s`;
  $("t0").value = t0;
}

$("change-actor").addEventListener("click", () => { clearSimulation(); state.actor = null; renderAll(); });
for (const button of $("strength").querySelectorAll("button")) {
  button.addEventListener("click", () => { clearSimulation(); state.params.decel = Number(button.dataset.decel); renderAll(); });
}
for (const button of $("target-simple").querySelectorAll("button")) {
  button.addEventListener("click", () => {
    clearSimulation();
    state.params.target = button.dataset.target; state.params.dwell = Number(button.dataset.dwell);
    renderAll();
  });
}
for (const [id, key, parse] of [["t0", "t0", Number], ["decel", "decel", Number], ["target", "target", String],
  ["dwell", "dwell", Number], ["reaction", "reaction", Number]]) {
  $(id).addEventListener("change", () => { clearSimulation(); state.params[key] = parse($(id).value); renderAll(); });
}
$("react").addEventListener("change", () => { clearSimulation(); state.params.react = $("react").checked; renderAll(); });
$("use-time").addEventListener("click", () => { clearSimulation(); state.params.t0 = Math.round(timeline.time * 20) / 20; renderAll(); });
$("run").addEventListener("click", () => runScenario());
$("replay").addEventListener("click", () => {
  timeline.setTime(Math.max(0, state.params.t0 - 2));
  if (!timeline.playing) timeline.toggle();
});
$("export").addEventListener("click", () => exportScenario());
$("sensitivity").addEventListener("click", () => runSensitivity());

// Leaving a result: the scene goes back to the recording (the parameters stay).
function clearSimulation() {
  if (!state.sim) return;
  state.sim = null;
  state.exported = null;
  state.sensitivity = null;
  eachView((v) => v.setScene(baseScene(), true));
  eachView((v) => v.setSelected(state.actor));
  applyLayers();
}

function requestParams() {
  const p = state.params;
  return { actor: state.actor, t0: p.t0, decel: p.decel, target: p.target, dwell: p.target === "stop" ? p.dwell : 0,
    react: p.react, reaction: p.reaction };
}

async function runScenario(params = null) {
  if (params) { clearSimulation(); state.actor = params.actor; state.params = { ...state.params, ...params }; }
  if (!state.actor) return;
  const request = ++state.request;
  toast("Đang mô phỏng…", false, 0);
  try {
    const sim = await simulateEvent(state.source, state.scene.name, requestParams());
    if (request !== state.request) return;
    state.sim = sim;
    state.exported = null;
    state.sensitivity = null;
    state.selected = state.actor;
    eachView((v) => v.setScene(variantScene(sim), true));
    eachView((v) => v.setSelected(state.actor));
    applyLayers();
    timeline.setTime(Math.max(0, state.params.t0 - 2));
    renderAll();
    toast("");
  } catch (error) {
    if (request === state.request) toast(error.message, true, 6000);
  }
}

// The scene as the scenario replays it: changed vehicles on their simulated motion, dashed ghosts where
// the braking vehicle and the ego were in the recording.
function variantScene(sim) {
  const tracks = state.scene.tracks.map((t) => {
    const copy = { ...t, pilot: t.name === "ego" ? t.gt : t.pilot };
    const changed = sim.changed[t.name];
    if (changed) {
      Object.assign(copy, { pilot: changed.poses, gt: changed.poses, actor: changed.role === "event",
        reacted: changed.role === "reacted" });
      if (changed.role === "event" || t.name === "ego") copy.ghost = t.name === "ego" ? t.gt : t.pilot;
    }
    return copy;
  });
  return { ...state.scene, tracks, variant: sim };
}

async function exportScenario() {
  const status = $("export-status");
  status.textContent = "Đang cho esmini chạy lại để kiểm tra, rồi đóng gói… (vài giây)";
  $("export").disabled = true;
  try {
    const out = await exportEvent(state.source, state.scene.name, requestParams());
    state.exported = out;
    const err = maxReplayError(out.report);
    status.innerHTML = out.report.valid
      ? `esmini chạy lại khớp${err != null ? ` (lệch tối đa ${metres(err, 3)})` : ""}. <a href="${out.download}">Tải lại file</a>`
      : `esmini báo lỗi: ${escapeHtml((out.report.esmini.problems || []).join("; ") || "xem report.json")}`;
    const link = document.createElement("a");
    link.href = out.download; link.download = `${out.id}.zip`;
    document.body.append(link); link.click(); link.remove();
    if (state.mode === "tech") renderDock(dockContext());
  } catch (error) {
    status.textContent = error.message;
  } finally {
    $("export").disabled = !state.sim?.result.valid;
  }
}

function maxReplayError(report) {
  const values = Object.values(report.esmini?.replay_error_m || {}).filter(Boolean).map((e) => e.max);
  return values.length ? Math.max(...values) : null;
}

async function runSensitivity() {
  $("sensitivity-out").innerHTML = '<div class="muted small">Đang chạy 3 lần…</div>';
  const rows = [];
  for (const reaction of [0.7, 1.0, 1.5]) {
    try {
      const sim = await simulateEvent(state.source, state.scene.name, { ...requestParams(), reaction });
      rows.push({ reaction, ...sim.result });
    } catch (error) {
      rows.push({ reaction, error: error.message });
    }
  }
  state.sensitivity = rows;
  renderSensitivity();
}

function renderSensitivity() {
  const rows = state.sensitivity;
  if (!rows) { $("sensitivity-out").innerHTML = ""; return; }
  $("sensitivity-out").innerHTML = `<table class="sens"><tr><th>Phản xạ</th><th>Kết quả</th><th>Xe bạn phanh</th><th>Gần nhất</th></tr>`
    + rows.map((r) => `<tr><td>${num(r.reaction, 1)} s</td><td>${r.error ? escapeHtml(r.error) : r.valid ? groupLabel(r.group) : '<span class="bad-text">không dùng được</span>'}</td>`
      + `<td>${r.ego?.a_used ? `${num(r.ego.a_used, 1)} m/s²` : "–"}</td><td>${r.ego?.min_gap != null ? metres(r.ego.min_gap, 1) : "–"}</td></tr>`).join("")
    + "</table>";
}

// ---------------------------------------------------------------- rendering
function renderAll() {
  renderSteps();
  renderForm();
  renderResult();
  renderFound();
  renderTopChips();
  renderDetails();
  drawMarkers();
  views.top.setOverlay(overlayAt(timeline.time));
  if (state.mode === "tech") renderDock(dockContext());
}

function renderSteps() {
  const step = state.sim ? 3 : state.actor ? 2 : 1;
  for (const k of [1, 2, 3]) {
    $(`step${k}`).classList.toggle("on", k === step);
    $(`step${k}`).classList.toggle("done", k < step);
  }
  const texts = {
    1: "Bấm vào một xe có <b>viền hồng</b>: những xe đang có xe khác chạy phía sau.",
    2: `Chọn cách <b>${escapeHtml(state.actor || "")}</b> phanh ở cột bên phải, rồi bấm <b>Tạo tình huống</b>.`,
    3: "Bấm <b>Phát lại</b> để xem các xe phía sau phản ứng, hoặc <b>Tải gói kịch bản</b>.",
  };
  $("banner").innerHTML = texts[step];
  $("banner").hidden = state.mode === "tech" || !state.scene;
}

function renderTopChips() {
  const scene = state.scene;
  const problems = Object.keys(scene?.label_problems || {});
  $("quality").hidden = !problems.length;
  $("quality").textContent = `${problems.length} xe có đoạn nhãn lỗi`;
  $("quality").title = `Nhãn gốc có chuyển động phi lý: ${problems.join(", ")} (xem tab "Dữ liệu gốc")`;
  const code = scene?.code;
  $("provenance").textContent = code?.commit ? `code ${code.commit.slice(0, 7)}${code.dirty ? " (đang sửa)" : ""}`
    + `${scene.run?.esmini ? ` · esmini ${scene.run.esmini}` : ""}` : "code chưa commit";
}

function renderForm() {
  const has = Boolean(state.actor);
  $("pick-help").hidden = has;
  $("form").hidden = !has;
  const names = Object.keys(state.scene?.selectable || {});
  $("pick-list").innerHTML = names.length
    ? names.map((n) => `<button data-pick="${escapeHtml(n)}">${escapeHtml(n)}</button>`).join("")
    : '<span class="muted">Cảnh này không có xe nào đang được xe khác chạy theo sau, nên chưa tạo được tình huống phanh.</span>';
  for (const b of $("pick-list").querySelectorAll("[data-pick]")) b.addEventListener("click", () => chooseActor(b.dataset.pick));
  if (!has) return;
  const p = state.params;
  const info = state.scene.selectable[state.actor] || { max_decel: 8, times: [p.t0] };
  $("actor-name").textContent = state.actor;
  $("t0-simple").textContent = `${num(p.t0, 1)} s`;
  for (const b of $("strength").querySelectorAll("button")) {
    const want = { Nhẹ: 2, Vừa: 4, Gấp: 6 }[b.textContent] ?? Number(b.dataset.decel);
    b.dataset.decel = String(Math.min(want, info.max_decel));
    b.classList.toggle("on", Number(b.dataset.decel) === p.decel);
  }
  for (const b of $("target-simple").querySelectorAll("button")) {
    b.classList.toggle("on", b.dataset.target === p.target && (p.target === "half" || Number(b.dataset.dwell) === p.dwell));
  }
  $("t0").value = p.t0; $("decel").value = p.decel; $("decel").max = info.max_decel;
  $("target").value = p.target; $("dwell").value = p.dwell; $("dwell").disabled = p.target !== "stop";
  $("reaction").value = p.reaction; $("react").checked = p.react;
  $("decel-note").textContent = `Xe này phanh tối đa ${num(info.max_decel, 0)} m/s²`
    + (info.max_decel < 8 ? " (xe buýt, xe tải)" : "")
    + `. Có xe theo sau trong khoảng ${num(info.times[0], 1)}–${num(info.times[info.times.length - 1], 1)} s.`;
}

function groupLabel(key) {
  return GROUPS.find((g) => g.key === key)?.label || key || "–";
}

// One plain sentence for the result, with a hint when it cannot be used.
function verdict(sim) {
  const r = sim.result, e = r.ego || {};
  const others = r.reacted.filter((n) => n !== sim.event.actor && n !== "ego").length;
  if (r.valid) {
    const gap = e.min_gap != null ? `${num(e.min_gap, 1)} m` : "–";
    const ttc = e.min_ttc != null && e.min_ttc < 10 ? ` (TTC ${num(e.min_ttc, 1)} s)` : "";
    const used = e.a_used ? `phanh ${num(e.a_used, 1)} m/s²` : "không phải phanh";
    const chain = others ? ` ${others} xe khác phía sau cũng phản ứng.` : "";
    const SIDE = { front: "phía trước", rear: "phía sau", left: "bên trái", right: "bên phải" };
    const partner = e.conflict_with ? `${e.conflict_with}${e.conflict_side ? ` (${SIDE[e.conflict_side]})` : ""}` : "xe khác";
    const how = e.close_by === "gap" ? `có lúc chỉ cách ${num(e.min_gap_path, 1)} m` : `có lúc chỉ còn ${num(e.min_ttc, 1)} s là chạm`;
    const texts = {
      close: ["rare", "Dùng được · ca hiếm: suýt chạm", `Xe của bạn ${used} và suýt chạm ${partner}: ${how}.${chain}`],
      hard: ["rare", "Dùng được · ca hiếm: phải phanh gấp", `Xe của bạn cần phanh ít nhất ${num(e.a_min, 1)} m/s² mới tránh được.${chain}`],
      mild: ["ok", "Dùng được: xe của bạn phanh nhẹ là đủ", `Xe của bạn ${used}, gần nhất ${gap}.${chain}`],
      far: ["ok", "Dùng được: xe của bạn không bị ảnh hưởng", `Xe của bạn giữ khoảng cách từ ${gap} trở lên.${chain}`],
      collision: ["bad", "Xe của bạn đâm vào", "Vì không ai phản ứng, kể cả xe của bạn (ô “Xe phía sau phản ứng” đang tắt)."],
    };
    const [kind, title, body] = texts[r.group] || ["ok", "Dùng được", ""];
    return { kind, title, body, tip: "" };
  }
  const reason = r.reasons[0];
  const hit = r.collisions?.[0];
  const label = Object.keys(r.details?.physics || {}).find((n) => (state.scene.label_problems || {})[n]);
  const texts = {
    collision: [hit ? crashText(sim, hit) : "Các xe khác đâm nhau.",
      "Thử phanh nhẹ hơn, hoặc chọn lúc xe phía sau cách xa hơn."],
    unsupported_interaction: ["Ở chỗ này có xe nhập làn, cắt ngang hoặc người đi bộ. Tool chưa mô phỏng được kiểu tương tác đó, nên không đưa ra kịch bản đoán bừa.",
      "Chọn lúc khác hoặc xe khác."],
    unsupported_appearing: ["Một xe đi vào khung hình đúng chỗ tình huống vừa bị thay đổi. Tool chưa biết trước đó nó ở đâu.",
      "Chọn lúc phanh sớm hơn hoặc muộn hơn."],
    label_error: [`Nhãn gốc của dữ liệu${label ? ` (${label})` : ""} bị lỗi ở đoạn này: kịch bản sẽ chứa chuyển động phi lý.`,
      "Chọn xe khác hoặc lúc khác."],
    physics: ["Có xe phải tăng tốc hoặc phanh vượt giới hạn vật lý.", "Thử phanh nhẹ hơn."],
    tailgating: ["Có xe bám sát xe trước dưới 0,5 m khi đang chạy; ngoài đời không ai lái như vậy.", "Thử phanh nhẹ hơn hoặc chọn lúc khác."],
  };
  const [body, tip] = texts[reason] || [r.reasons.join(", "), ""];
  return { kind: "bad", title: "Không dùng được", body, tip };
}

// "car_010 (phía sau) đâm vào car_006 lúc 3,1 s, dù đã phanh 7,0 m/s² (tối đa của xe là 8)": the vehicle that
// did not change first is the one hit; of two reacting ones, the one that braked later hit the other.
function crashText(sim, [a, b, t]) {
  const reacts = Object.fromEntries(sim.markers.filter((m) => m.kind === "reacts").map((m) => [m.agent, m.t]));
  const behind = a === sim.event.actor ? b : b === sim.event.actor ? a : (reacts[a] ?? 0) >= (reacts[b] ?? 0) ? a : b;
  const front = behind === a ? b : a;
  const used = sim.result.max_decel_used?.[behind];
  const limit = state.scene.drivers?.[behind]?.max_decel;
  const braking = used ? `, dù đã phanh ${num(used, 1)} m/s²${limit ? ` (tối đa của xe là ${num(limit, 0)})` : ""}` : "";
  return `${behind} (xe phía sau) đâm vào ${front} lúc ${num(t, 1)} s${braking}. Xe sau bám quá sát nên không kịp dừng.`;
}

function renderResult() {
  const sim = state.sim;
  $("result").hidden = !sim;
  $("run").hidden = Boolean(sim);
  if (!sim) { $("export-status").textContent = ""; return; }
  const v = verdict(sim);
  $("verdict").className = `verdict ${v.kind}`;
  const groupHelp = sim.result.valid && ["close", "hard"].includes(sim.result.group) ? helpIcon(sim.result.group) : "";
  $("verdict").innerHTML = `<b>${escapeHtml(v.title)}${groupHelp}</b>${escapeHtml(v.body)}${v.tip ? `<span class="tip">${escapeHtml(v.tip)}</span>` : ""}`;
  $("export").disabled = !sim.result.valid;
  $("export").title = sim.result.valid ? "" : "Chỉ tải được tình huống dùng được";
  const r = sim.result, e = r.ego || {};
  $("result-kv").innerHTML = [
    [`Hợp lệ${helpIcon("valid")}`, r.valid ? '<span class="tag ok">có · đạt mọi điều kiện</span>' : `<span class="tag bad">không · ${escapeHtml(r.reasons.join(", "))}</span>`],
    [`Nhóm${helpIcon("group")}`, groupLabel(r.group)],
    [`Gần nhất${helpIcon("min_gap")} · TTC nhỏ nhất${helpIcon("ttc")}`, `${e.min_gap != null ? metres(e.min_gap, 2) : "–"} · ${e.min_ttc != null ? seconds(e.min_ttc) : "–"}`],
    [`Xe bạn cần / đã phanh${helpIcon("braking")}`, `${e.a_min != null ? num(e.a_min, 1) : "–"} / ${e.a_used ? num(e.a_used, 1) : "0"} m/s²`],
    [`Suýt chạm / gần nhất với`, e.conflict_with ? `${escapeHtml(e.conflict_with)} (${{ front: "phía trước", rear: "phía sau", left: "bên trái", right: "bên phải" }[e.conflict_side] || "–"})` : "–"],
    [`Cùng cặp xe trong bản ghi${helpIcon("recorded_gap")}`, e.recorded_min_gap != null ? `gần nhất ${metres(e.recorded_min_gap, 2)}` : "–"],
    [`Xe phản ứng${helpIcon("reacted")}`, `${r.reacted.filter((n) => n !== sim.event.actor).length} (phản xạ ${num(sim.event.reaction, 1)} s)`],
  ].map(([k, val]) => `<dt>${k}</dt><dd>${val}</dd>`).join("");
  const th = state.scene.thresholds || {};
  const tag = (measured) => `<span class="tag ${measured ? "ok" : ""}">${measured ? "đo" : "mặc định"}</span>`;
  const driverRows = Object.keys(sim.changed).map((name) => {
    const d = state.scene.drivers?.[name];
    return d ? `<dt>${escapeHtml(name)}: T · s₀${helpIcon("T_s0")}</dt><dd>${num(d.T, 2)} s${tag(d.T_measured)} · ${num(d.s0, 1)} m${tag(d.s0_measured)}</dd>` : "";
  }).join("");
  $("drivers-kv").innerHTML = `<dt>Phản xạ${helpIcon("reaction")}</dt><dd>${num(sim.event.reaction, 1)} s</dd>`
    + `<dt>IDM tăng tốc / phanh thoải mái${helpIcon("idm")}</dt><dd>${num(th.idm_a, 1)} / ${num(th.idm_b, 1)} m/s²</dd>`
    + `<dt>Phanh tối đa xe con / xe nặng${helpIcon("max_decel")}</dt><dd>${num(th.max_decel, 0)} / ${num(th.heavy_max_decel, 0)} m/s²</dd>`
    + `<dt>Độ giật khi phanh${helpIcon("jerk")}</dt><dd>${num(th.jerk_brake, 0)} m/s³</dd>` + driverRows;
  renderSensitivity();
}

// "Ca hiếm tìm sẵn": the processed grid of this scene, most interesting first.
function renderFound() {
  const box = $("found");
  const data = state.scene?.variants?.pilot;
  if (!state.scene) { box.innerHTML = ""; return; }
  if (!data) {
    box.innerHTML = `<div class="callout">Cảnh này chưa được xử lý, nên tool chưa tự thử các cách phanh.
      <div class="row gap"><button id="process-this" class="primary">Xử lý cảnh này</button></div></div>`;
    $("process-this").addEventListener("click", () => startProcessing([state.scene.name]));
    return;
  }
  const s = data.summary;
  const rank = { hard: 0, close: 1, mild: 2, far: 3 };
  // one row per braking moment (vehicle and start time): its most dangerous valid variant
  const seen = new Set();
  const rows = [...data.cases].sort((a, b) => (rank[a.group] - rank[b.group]) || ((a.min_gap ?? 99) - (b.min_gap ?? 99)))
    .filter((c) => { const key = `${c.actor}@${c.t0}`; if (seen.has(key)) return false; seen.add(key); return true; })
    .slice(0, 10);
  box.innerHTML = `<p class="small">Tool đã tự thử <b>${s.attempted}</b> cách phanh trong cảnh này: <b>${s.valid}</b> dùng được,
    trong đó <b>${s.valuable}</b> là ca hiếm (trong ${s.valuable_encounters} lần phanh). Mỗi dòng dưới đây là một lần phanh khác nhau,
    với cách phanh nguy hiểm nhất của nó:</p>`
    + `<ul class="found-list">${rows.map((c) => `<li><div><b>${escapeHtml(c.actor)}</b> phanh ${num(c.decel, 0)} m/s² lúc ${num(c.t0, 0)} s,
      ${c.target === "stop" ? (c.dwell ? `dừng ${num(c.dwell, 0)} s` : "dừng hẳn") : "chậm lại"}
      <div class="what ${rank[c.group] < 2 ? "danger" : ""}">${groupLabel(c.group)}${c.min_gap != null ? ` · gần nhất ${metres(c.min_gap, 1)}` : ""}</div></div>
      <button data-found="${escapeHtml(c.id)}">Xem</button></li>`).join("")}</ul>`
    + (s.valuable ? `<a class="small" href="${rareUrl(state.source, state.scene.name)}">Tải cả ${s.valuable} ca hiếm (.zip)</a>` : "");
  for (const b of box.querySelectorAll("[data-found]")) {
    const c = data.cases.find((x) => x.id === b.dataset.found);
    b.addEventListener("click", () => {
      showTab("create");
      runScenario({ actor: c.actor, t0: c.t0, decel: c.decel, target: c.target, dwell: c.dwell, react: true, reaction: 1.0 });
    });
  }
}

for (const button of document.querySelectorAll("[data-tab]")) button.addEventListener("click", () => showTab(button.dataset.tab));
function showTab(name) {
  for (const b of document.querySelectorAll("[data-tab]")) b.classList.toggle("on", b.dataset.tab === name);
  $("tab-create").hidden = name !== "create";
  $("tab-found").hidden = name !== "found";
}

// ---------------------------------------------------------------- selected object (technical mode)
let deviation = null;
function renderDetails() {
  const box = $("details");
  const track = trackByName(state.selected);
  if (!track) { box.className = "details muted"; box.textContent = "Bấm vào một vật thể trên khung xem."; deviation = null; return; }
  box.className = "details";
  const [length, width, height] = track.size;
  const span = track.gt.t[track.gt.t.length - 1] - track.gt.t[0];
  const driver = state.scene.drivers?.[track.name];
  const problems = state.scene.label_problems?.[track.name];
  const used = state.sim?.result.max_decel_used?.[track.name];
  const errors = Object.entries(track.errors || {}).filter(([, e]) => e)
    .map(([m, e]) => `<tr><td>Sai số phát lại (${m})${helpIcon("ade")}</td><td>${metres(e.ade)} · tối đa ${metres(e.max)}</td></tr>`).join("");
  deviation = { track, series: deviationSeries(track) };
  box.innerHTML = `<div class="title">${escapeHtml(track.name)}</div>
    <table>
      <tr><td>Loại</td><td>${KIND_LABEL[track.kind] || escapeHtml(track.kind)} · ${escapeHtml(track.category)}</td></tr>
      <tr><td>Dài × rộng × cao</td><td>${num(length, 1)} × ${num(width, 1)} × ${num(height, 1)} m</td></tr>
      <tr><td>Có dữ liệu</td><td>${track.keyframes} mốc nhãn · ${num(span, 1)} s${track.stationary ? " · đứng yên" : ""}</td></tr>
      ${errors}
      ${problems ? `<tr><td>Nhãn lỗi${helpIcon("label_problem")}</td><td class="warn-text">${problems.map(([a, b]) => `${num(a, 1)}–${num(b, 1)} s`).join(", ")}</td></tr>` : ""}
      ${driver ? `<tr><td>Người lái mẫu: T · s₀${helpIcon("T_s0")}</td><td>${num(driver.T, 2)} s · ${num(driver.s0, 1)} m</td></tr>
        <tr><td>Phanh tối đa</td><td>${num(driver.max_decel, 0)} m/s²</td></tr>` : ""}
      ${used != null ? `<tr><td>Trong tình huống: phanh mạnh nhất</td><td>${num(used, 1)} m/s²</td></tr>` : ""}
    </table>
    <div class="dev-title small muted">Quỹ đạo dựng lại lệch so với nhãn lúc <span id="dev-time"></span>: <span id="dev-values"></span></div>
    <canvas id="dev-chart" class="chart" style="height:80px"></canvas>`;
  renderDeviation();
}

function renderDeviation() {
  if (!deviation || !$("dev-values")) return;
  const t = timeline.time;
  $("dev-time").textContent = `${num(t, 1)} s`;
  const d = deviationAt(deviation.track, "pilot", t);
  $("dev-values").textContent = d ? metres(d.distance, 2) : "không có dữ liệu";
  drawDeviationChart($("dev-chart"), deviation.series, t, {
    pilot: getCss("--accent"), baseline: getCss("--obj-baseline"), now: getCss("--obj-selected"), grid: getCss("--border"), text: getCss("--muted"),
  });
}

// ---------------------------------------------------------------- dock (technical mode)
for (const button of document.querySelectorAll("[data-dock]")) {
  button.addEventListener("click", () => {
    state.dock = button.dataset.dock;
    for (const b of document.querySelectorAll("[data-dock]")) b.classList.toggle("on", b === button);
    renderDock(dockContext());
  });
}

function dockContext() {
  return {
    tab: state.dock, scene: state.scene, sim: state.sim, exported: state.exported, actor: state.actor,
    params: state.params, time: timeline.time, body: $("dock-body"), source: state.source,
    setTime: (t) => timeline.setTime(t),
    select: (name) => { state.selected = name; eachView((v) => v.setSelected(name)); renderDetails(); },
    open: (params) => runScenario(params),
  };
}

// ---------------------------------------------------------------- keyboard
document.addEventListener("keydown", (e) => {
  if (e.target.matches?.("input, select, textarea")) return;
  if (e.key === " ") { e.preventDefault(); timeline.toggle(); }
  if (e.key === "ArrowLeft") timeline.setTime(timeline.time - (e.shiftKey ? 1 : 0.05));
  if (e.key === "ArrowRight") timeline.setTime(timeline.time + (e.shiftKey ? 1 : 0.05));
  if (e.key === "Escape") $("data-dialog").hidden = true;
});
window.addEventListener("resize", () => drawMarkers());

// Handy in the browser console (F12) when debugging.
window.real2sim = { views, timeline, state, setMode, runScenario };

initHelp();

(async () => {
  try {
    const status = await getStatus();
    $("esmini-warning").hidden = Boolean(status.esmini);
    await loadSources();
    await pollJobs();
  } catch (error) {
    toast(`Không kết nối được máy chủ: ${error.message}`, true, 0);
  }
})();
