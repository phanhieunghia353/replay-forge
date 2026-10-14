// The technical mode's dock (docs/thiet-ke-giao-dien.md, section 5): seven tabs that answer what a test
// engineer asks about a scenario. renderDock(ctx) draws the active tab into ctx.body; with timeOnly set
// (the timeline moved) only what follows the current time is redrawn.

import { drawChart, onChartClick } from "./charts.js";
import { GROUPS, REASON_LABEL, escapeHtml, metres, num } from "./format.js";
import { helpIcon } from "./help.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const ui = { qty: "speed", method: "pilot", spaceActor: null, spaceTarget: "stop|0", sort: { data: ["name", 1], space: ["t0", 1] } };
let last = null;

export function renderDock(ctx, timeOnly = false) {
  last = ctx;
  if (timeOnly) {
    if (ctx.tab === "chart") drawCharts(ctx);
    return;
  }
  const body = ctx.body;
  if (!ctx.scene) { body.innerHTML = ""; return; }
  ({ chart: tabChart, space: tabSpace, vehicles: tabVehicles, checks: tabChecks, esmini: tabEsmini,
    data: tabData, export: tabExport })[ctx.tab](ctx, body);
}

const roleColour = (sim, name) => (name === "ego" ? css("--obj-ego")
  : sim.changed[name]?.role === "event" ? css("--obj-actor") : css("--obj-reacted"));
const needSim = (body) => {
  body.innerHTML = '<p class="muted">Tạo một tình huống (cột bên phải) để xem phần này.</p>';
};

// ---------------------------------------------------------------- 1. charts
function tabChart(ctx, body) {
  if (!ctx.sim) return needSim(body);
  const chips = [["speed", "Tốc độ"], ["accel", "Gia tốc"], ["gap", "Khoảng cách và TTC của xe bạn"]]
    .map(([k, label]) => `<button class="chip ${ui.qty === k ? "on" : ""}" data-qty="${k}">${label}</button>`).join("");
  body.innerHTML = `<div class="bar">${chips}${helpIcon("ttc")}<span class="spacer"></span><span class="muted small">Nét đứt: bản ghi gốc. Bấm vào biểu đồ để tới thời điểm đó.</span></div>
    <canvas id="chart-a" class="chart"></canvas><canvas id="chart-b" class="chart" style="height:90px"></canvas>`;
  for (const b of body.querySelectorAll("[data-qty]")) b.addEventListener("click", () => { ui.qty = b.dataset.qty; tabChart(ctx, body); });
  for (const id of ["chart-a", "chart-b"]) onChartClick(body.querySelector(`#${id}`), (t) => last.setTime(t));
  drawCharts(ctx);
}

function drawCharts(ctx) {
  const a = ctx.body.querySelector("#chart-a"), b = ctx.body.querySelector("#chart-b");
  if (!a || !ctx.sim) return;
  const sim = ctx.sim, th = ctx.scene.thresholds || {};
  const names = Object.keys(sim.series);
  b.hidden = ui.qty !== "gap";
  if (ui.qty === "speed") {
    const series = names.map((n) => ({ values: sim.series[n].v, colour: roleColour(sim, n), label: n }));
    for (const n of [sim.event.actor, "ego"]) {
      if (sim.series[n]) series.push({ values: sim.series[n].v_rec, colour: roleColour(sim, n), dash: true });
    }
    drawChart(a, { t: sim.t, series, now: ctx.time, unit: "m/s", yMin: 0 });
  } else if (ui.qty === "accel") {
    const series = names.map((n) => ({ values: sim.series[n].a, colour: roleColour(sim, n), label: n }));
    drawChart(a, { t: sim.t, series, now: ctx.time, unit: "m/s²", thresholds: [
      { value: -(th.comfort_decel ?? 3.4), label: `phanh thoải mái −${num(th.comfort_decel ?? 3.4, 1)}`, colour: css("--warn") },
      { value: -(th.max_decel ?? 8), label: `phanh gấp tối đa −${num(th.max_decel ?? 8, 0)}`, colour: css("--danger") },
      { value: th.valid_max_accel ?? 4, label: `tăng tốc tối đa ${num(th.valid_max_accel ?? 4, 0)}`, colour: css("--danger") }] });
  } else {
    const ego = sim.series.ego;
    drawChart(a, { t: sim.t, series: [{ values: ego.gap, colour: css("--obj-ego"), label: "khoảng cách tới xe trước (m)" }],
      now: ctx.time, unit: "m", yMin: 0, thresholds: [{ value: th.close_gap_m ?? 1, label: "suýt chạm < 1 m", colour: css("--danger") }] });
    drawChart(b, { t: sim.t, series: [{ values: ego.ttc.map((v) => (v == null ? null : Math.min(v, 10))), colour: css("--obj-leader"), label: "TTC (s, cắt ở 10)" }],
      now: ctx.time, unit: "s", yMin: 0, yMax: 10, thresholds: [{ value: th.close_ttc_s ?? 1.5, label: "TTC < 1,5 s", colour: css("--danger") }] });
  }
}

// ---------------------------------------------------------------- 2. parameter space
const CELL = { close: "#e24b4a", hard: "#a32d2d", mild: "#ef9f27", far: "#b4b2a9", collision: "#501313" };

function tabSpace(ctx, body) {
  const data = ctx.scene.variants?.[ui.method];
  if (!data) { body.innerHTML = '<p class="muted">Cảnh này chưa được xử lý (nút “Dữ liệu…” → Xử lý), nên chưa có lưới tham số.</p>'; return; }
  const actors = [...new Set(data.grid.map((r) => r.actor))];
  const ev = ctx.sim?.event;
  if (ev && ev.id !== ui.spaceFor) {  // follow the scenario on screen until the user picks something else
    ui.spaceFor = ev.id;
    if (actors.includes(ev.actor)) ui.spaceActor = ev.actor;
    ui.spaceTarget = ev.target === "half" ? "half|0" : `stop|${ev.dwell >= 3 ? 3 : 0}`;
  }
  if (!actors.includes(ui.spaceActor)) ui.spaceActor = actors.includes(ctx.actor) ? ctx.actor : actors[0];
  const [target, dwell] = ui.spaceTarget.split("|");
  const rows = data.grid.filter((r) => r.actor === ui.spaceActor && r.target === target && (target === "half" || r.dwell === Number(dwell)));
  const decels = [...new Set(data.grid.filter((r) => r.actor === ui.spaceActor).map((r) => r.decel))].sort((x, y) => y - x);
  const times = [...new Set(data.grid.filter((r) => r.actor === ui.spaceActor).map((r) => r.t0))].sort((x, y) => x - y);
  const cur = ctx.sim?.event;
  let grid = `<div class="heat" style="grid-template-columns: 36px repeat(${times.length}, minmax(28px, 1fr))">`;
  for (const d of decels) {
    grid += `<div class="axis">${num(d, 0)}</div>`;
    for (const t of times) {
      const r = rows.find((x) => x.decel === d && x.t0 === t);
      if (!r) { grid += "<div></div>"; continue; }
      const isCur = cur && cur.actor === r.actor && cur.t0 === r.t0 && cur.decel === r.decel && cur.target === r.target && cur.dwell === r.dwell;
      const style = r.valid ? `background:${CELL[r.group] || "#ccc"}` : "background:repeating-linear-gradient(45deg,#eee,#eee 3px,#fff 3px,#fff 6px);border-color:#ccc";
      const title = r.valid ? `${groupName(r.group)}${r.min_gap != null ? ` · gần nhất ${num(r.min_gap, 1)} m` : ""}`
        : `không dùng được: ${r.reasons.map((x) => REASON_LABEL[x] || x).join("; ")}`;
      grid += `<div class="cell ${isCur ? "cur" : ""}" style="${style}" title="phanh ${num(d, 0)} m/s² lúc ${num(t, 0)} s: ${escapeHtml(title)}" data-id="${escapeHtml(r.id)}"></div>`;
    }
  }
  grid += `<div></div>${times.map((t) => `<div class="axis">${num(t, 0)}</div>`).join("")}</div>`;
  const legend = [["close", "suýt chạm"], ["hard", "phải phanh gấp"], ["mild", "phanh nhẹ"], ["far", "không ảnh hưởng"], ["collision", "xe bạn đâm (không phản ứng)"]]
    .map(([k, l]) => `<div><i class="sw" style="background:${CELL[k]}"></i> ${l}</div>`).join("")
    + '<div><i class="sw" style="border:1px dashed #999"></i> không dùng được (rê chuột để xem lý do)</div>';
  const all = data.grid.filter((r) => r.actor === ui.spaceActor);
  body.innerHTML = `<div class="bar">
      <select id="sp-method"><option value="pilot">Có phản ứng (pilot)</option><option value="baseline">Không ai phản ứng (baseline)</option></select>
      <select id="sp-actor">${actors.map((a) => `<option ${a === ui.spaceActor ? "selected" : ""}>${escapeHtml(a)}</option>`).join("")}</select>
      <select id="sp-target"><option value="stop|0">dừng hẳn</option><option value="stop|3">dừng 3 s</option><option value="half|0">chậm lại còn nửa</option></select>
      <span class="muted small">Trục dọc: mức phanh (m/s²) · trục ngang: lúc bắt đầu phanh (s). Bấm một ô để mở.</span>${helpIcon("space")}</div>
    <div class="two"><div>${grid}</div><div class="small">${legend}</div></div>
    <h3>Mọi biến thể của ${escapeHtml(ui.spaceActor)} (${all.length})</h3>${spaceTable(all, cur)}`;
  body.querySelector("#sp-method").value = ui.method;
  body.querySelector("#sp-target").value = ui.spaceTarget;
  body.querySelector("#sp-method").addEventListener("change", (e) => { ui.method = e.target.value; tabSpace(ctx, body); });
  body.querySelector("#sp-actor").addEventListener("change", (e) => { ui.spaceActor = e.target.value; tabSpace(ctx, body); });
  body.querySelector("#sp-target").addEventListener("change", (e) => { ui.spaceTarget = e.target.value; tabSpace(ctx, body); });
  const open = (id) => {
    const r = data.grid.find((x) => x.id === id);
    ctx.open({ actor: r.actor, t0: r.t0, decel: r.decel, target: r.target, dwell: r.dwell, react: ui.method === "pilot", reaction: 1.0 });
  };
  for (const cell of body.querySelectorAll(".cell")) cell.addEventListener("click", () => open(cell.dataset.id));
  for (const row of body.querySelectorAll("tr[data-id]")) row.addEventListener("click", () => open(row.dataset.id));
  bindSort(body, "space", () => tabSpace(ctx, body));
}

function spaceTable(rows, cur) {
  const cols = [["t0", "Lúc (s)", true], ["decel", "Phanh (m/s²)", true], ["target", "Đích", false], ["valid", "Dùng được", false],
    ["group", "Nhóm", false], ["min_gap", "Gần nhất (m)", true], ["a_used", "Xe bạn phanh", true], ["reasons", "Lý do loại", false]];
  const sorted = sortRows(rows, "space");
  return `<table class="t">${header(cols, "space")}${sorted.map((r) => `<tr class="click" data-id="${escapeHtml(r.id)}"${cur && cur.decel === r.decel && cur.t0 === r.t0 && cur.target === r.target && cur.dwell === r.dwell ? ' style="font-weight:600"' : ""}>
    <td class="num">${num(r.t0, 0)}</td><td class="num">${num(r.decel, 0)}</td><td>${r.target === "stop" ? (r.dwell ? `dừng ${num(r.dwell, 0)} s` : "dừng") : "nửa tốc độ"}</td>
    <td>${r.valid ? '<span class="ok-text">có</span>' : '<span class="bad-text">không</span>'}</td><td>${r.valid ? groupName(r.group) : ""}</td>
    <td class="num">${r.min_gap != null ? num(r.min_gap, 2) : "–"}</td><td class="num">${r.a_used ? num(r.a_used, 1) : "–"}</td>
    <td class="small">${r.reasons.map((x) => REASON_LABEL[x] || x).join("; ")}</td></tr>`).join("")}</table>`;
}

const groupName = (key) => GROUPS.find((g) => g.key === key)?.label || key;

// ---------------------------------------------------------------- 3. vehicles
const MODE_COLOUR = { nominal: "#d3d1c7", waiting: "#fac775", driving: null, late: "#5dcaa5", event: null };

function tabVehicles(ctx, body) {
  if (!ctx.sim) return needSim(body);
  const sim = ctx.sim, duration = ctx.scene.duration;
  const gaps = sim.result.details?.gaps || {};
  const reacts = Object.fromEntries(sim.markers.filter((m) => m.kind === "reacts").map((m) => [m.agent, m.t]));
  const rows = Object.entries(sim.changed).map(([name, info]) => {
    const d = ctx.scene.drivers?.[name] || {};
    const colour = roleColour(sim, name);
    const bar = info.modes.map(([a, b, m]) => `<i style="left:${(100 * a) / duration}%;width:${Math.max(0.4, (100 * (b - a + 0.05)) / duration)}%;background:${MODE_COLOUR[m] || colour}" title="${m} ${num(a, 1)}–${num(b, 1)} s"></i>`).join("");
    const leaders = [...new Set(info.leaders.map((s) => s[2]))].join(", ") || "–";
    const used = sim.result.max_decel_used?.[name];
    const g = gaps[name];
    const role = name === "ego" ? "xe của bạn" : info.role === "event" ? "gây tình huống" : "phản ứng";
    return `<tr class="click" data-name="${escapeHtml(name)}"><td><b style="color:${colour}">${escapeHtml(name)}</b></td><td>${role}</td>
      <td><div class="modebar">${bar}</div></td><td class="num">${reacts[name] != null ? num(reacts[name], 2) : "–"}</td>
      <td>${escapeHtml(leaders)}</td>
      <td class="num">${d.T != null ? `${num(d.T, 2)} · ${num(d.s0, 1)} ${d.T_measured || d.s0_measured ? '<span class="tag ok">đo</span>' : '<span class="tag">mặc định</span>'}` : "–"}</td>
      <td class="num">${used != null ? `${num(used, 1)} / ${num(d.max_decel ?? 8, 0)}` : "–"}</td>
      <td class="num">${g ? `${num(g.gap, 2)} m lúc ${num(g.t, 1)} s` : "–"}</td></tr>`;
  }).join("");
  body.innerHTML = `<table class="t"><tr><th>Xe</th><th>Vai trò</th><th style="width:28%">Trạng thái theo thời gian${helpIcon("modes")}</th><th class="num">Bắt đầu tự lái (s)</th>
    <th>Xe phía trước</th><th class="num">T (s) · s₀ (m)${helpIcon("T_s0")}</th><th class="num">Phanh mạnh nhất / giới hạn (m/s²)${helpIcon("max_decel")}</th><th class="num">Gần xe trước nhất (dọc đường đi)</th></tr>${rows}</table>
    <p class="muted small"><i class="sw" style="background:#d3d1c7"></i> theo bản ghi · <i class="sw" style="background:#fac775"></i> đang phản xạ
    · <i class="sw" style="background:${css("--obj-reacted")}"></i> tự lái (mô hình người lái) · <i class="sw" style="background:#5dcaa5"></i> quay lại kế hoạch, trễ hơn bản ghi.
    Bấm một dòng để chọn xe đó.</p>`;
  for (const row of body.querySelectorAll("tr[data-name]")) row.addEventListener("click", () => ctx.select(row.dataset.name));
}

// ---------------------------------------------------------------- 4. checks
function tabChecks(ctx, body) {
  if (!ctx.sim) return needSim(body);
  const r = ctx.sim.result, d = r.details || {}, th = ctx.scene.thresholds || {};
  const has = (reason) => r.reasons.includes(reason);
  const status = (bad, text = bad ? "không đạt" : "đạt") => `<span class="${bad ? "bad-text" : "ok-text"}">${text}</span>`;
  const jump = (t) => (t != null ? `<button class="link" data-t="${t}">${num(t, 2)} s</button>` : "–");
  let worst = null;
  for (const [name, p] of Object.entries(d.physics || {})) {
    if (p.max_decel != null && (!worst || p.max_decel / p.limit_decel > worst.ratio)) worst = { name, ...p, ratio: p.max_decel / p.limit_decel };
  }
  const hits = (kind) => r.collisions.filter((c) => c[3] === kind);
  const closest = Object.entries(d.gaps || {}).filter(([n]) => n !== "ego").sort((a, b) => a[1].gap - b[1].gap)[0];
  const exported = ctx.exported?.report;
  const rows = [
    [`esmini chạy hết, log đủ mọi vật thể${helpIcon("c_esmini")}`, "mã thoát 0", exported ? `mã ${exported.esmini.exit}${exported.esmini.problems?.length ? ` · ${escapeHtml(exported.esmini.problems[0])}` : ""}` : "chạy khi bấm “Tải gói kịch bản”",
      null, exported ? status(!exported.valid) : '<span class="muted">chưa chạy</span>'],
    [`Tăng tốc, phanh trong giới hạn của từng loại xe${helpIcon("c_physics")}`, `tăng ≤ ${num(th.valid_max_accel, 0)}; phanh ≤ giới hạn xe + ${num(th.valid_decel_slack, 1)} m/s²`,
      worst ? `phanh ${num(worst.max_decel, 1)} / ${num(worst.limit_decel, 1)} (${escapeHtml(worst.name)})` : "–", worst?.t_decel, status(has("physics"))],
    [`Nhãn gốc không lỗi ở đoạn bị thay đổi${helpIcon("c_label")}`, `trong ${num(th.label_reach_m, 0)} m dọc đường đi`, has("label_error") ? "có lỗi trong nhãn" : "không", null, status(has("label_error"))],
    [`Không xe nào đâm nhau (trừ xe của bạn)${helpIcon("c_collision")}`, "chồng hộp 0 m", hits("following").length ? `${escapeHtml(hits("following")[0][0])} × ${escapeHtml(hits("following")[0][1])}`
      : closest ? `gần nhất ${num(closest[1].gap, 2)} m (${escapeHtml(closest[0])})` : "–", hits("following")[0]?.[2] ?? closest?.[1].t, status(has("collision"))],
    [`Chồng hộp có sẵn trong bản ghi, được miễn${helpIcon("c_excused")}`, `cùng vị trí tương đối (±${num(th.exempt_along_m, 1)} m dọc, ±${num(th.exempt_across_m, 2)} m ngang)`,
      d.excused?.length ? d.excused.map((e) => `${escapeHtml(e[0])} × ${escapeHtml(e[1])}`).join(", ") : "không có", d.excused?.[0]?.[2], d.excused?.length ? '<span class="warn-text">miễn</span>' : status(false)],
    [`Không bám sát phi lý${helpIcon("c_tailgate")}`, `< ${num(th.tailgate_gap_m, 1)} m khi > ${num(th.tailgate_speed_mps, 0)} m/s quá ${num(th.tailgate_time_s, 1)} s`, has("tailgating") ? "có" : "không", null, status(has("tailgating"))],
    [`Không nhập làn, cắt ngang, người đi bộ ở chỗ va chạm${helpIcon("c_merge")}`, `lệch hướng > 30° trong ${num(th.merge_lookback_s, 0)} s`, hits("crossing").length ? `${escapeHtml(hits("crossing")[0][0])} × ${escapeHtml(hits("crossing")[0][1])}` : "không",
      hits("crossing")[0]?.[2], status(has("unsupported_interaction"), has("unsupported_interaction") ? "chưa hỗ trợ" : "đạt")],
    [`Không có xe vừa vào khung hình đúng chỗ tình huống${helpIcon("c_appear")}`, `${num(th.appear_window_s, 0)} s sau khi xuất hiện`, hits("appearing").length ? `${escapeHtml(hits("appearing")[0][0])} × ${escapeHtml(hits("appearing")[0][1])}` : "không",
      hits("appearing")[0]?.[2], status(has("unsupported_appearing"), has("unsupported_appearing") ? "chưa hỗ trợ" : "đạt")],
  ];
  body.innerHTML = `<table class="t"><tr><th style="width:30%">Điều kiện</th><th>Ngưỡng</th><th>Đo được (xấu nhất)</th><th>Lúc</th><th>Kết quả</th></tr>
    ${rows.map(([a, b, c, t, s]) => `<tr><td>${a}</td><td class="small">${b}</td><td>${c}</td><td>${jump(t)}</td><td>${s}</td></tr>`).join("")}</table>
    <p class="muted small">Bấm cột “Lúc” để tới khoảnh khắc đó. Ngưỡng nằm ở mục 9 của docs/gia-dinh-va-chi-so.md.</p>`;
  for (const b of body.querySelectorAll("[data-t]")) b.addEventListener("click", () => ctx.setTime(Number(b.dataset.t)));
}

// ---------------------------------------------------------------- 5. esmini replay
function tabEsmini(ctx, body) {
  const report = ctx.exported?.report;
  if (!report) {
    body.innerHTML = `<p class="muted">esmini chưa chạy tình huống này. Bấm <b>Tải gói kịch bản</b> ở cột bên phải: tool cho esmini phát lại file
      vừa tạo, đo nó lệch bao nhiêu so với quỹ đạo định đưa, rồi mới đóng gói.</p>`;
    return;
  }
  const e = report.esmini, dyn = e.dynamics || {};
  body.innerHTML = `<div class="two"><table class="t"><tr><th>Xe</th><th class="num">Lệch trung bình (m)${helpIcon("esmini_err")}</th><th class="num">Lệch tối đa (m)</th></tr>
    ${Object.entries(e.replay_error_m || {}).map(([n, v]) => `<tr><td>${escapeHtml(n)}</td><td class="num">${v ? num(v.mean, 4) : "–"}</td><td class="num">${v ? num(v.max, 4) : "–"}</td></tr>`).join("")}</table>
    <dl class="kv"><dt>esmini</dt><dd>${escapeHtml(e.version || "?")} · mã thoát ${e.exit}</dd>
      <dt>Bước thời gian</dt><dd>0,05 s · traj_filter 0</dd>
      <dt>Gia tốc lớn nhất: mô phỏng${helpIcon("esmini_acc")}</dt><dd>${num(dyn.sim, 2)} m/s²</dd>
      <dt>… trong esmini (thô)</dt><dd>${num(dyn.esmini_raw, 2)} m/s²</dd>
      <dt>… trong esmini (trung bình 0,2 s)</dt><dd>${num(dyn.esmini_smoothed, 2)} m/s²</dd>
      <dt>Cảnh báo</dt><dd>${e.problems?.length ? escapeHtml(e.problems.join("; ")) : "không"}</dd></dl></div>
    <p class="muted small">esmini giữ tốc độ không đổi giữa hai điểm quỹ đạo, nên gia tốc đo thô trong esmini hơi nhảy bậc; trung bình 0,2 s thì khớp mô phỏng.</p>`;
}

// ---------------------------------------------------------------- 6. source data
function tabData(ctx, body) {
  const problems = ctx.scene.label_problems || {};
  const rows = ctx.scene.tracks.map((t) => ({
    name: t.name, category: t.category, keyframes: t.keyframes, start: t.gt.t[0], end: t.gt.t[t.gt.t.length - 1],
    stationary: t.stationary, ade: t.errors?.pilot?.ade ?? null, max: t.errors?.pilot?.max ?? null, problems: problems[t.name] || null,
  }));
  const cols = [["name", "Vật thể", true], ["category", "Loại", true], ["keyframes", `Mốc nhãn${helpIcon("keyframes")}`, true],
    ["start", "Có mặt (s)", true], ["stationary", "Đứng yên", true], ["ade", `Sai số phát lại pilot (m)${helpIcon("ade")}`, true],
    ["max", "Tối đa (m)", true], ["problems", `Nhãn lỗi${helpIcon("label_problem")}`, true]];
  const sorted = sortRows(rows, "data");
  const s = ctx.scene.summary?.pilot?.moving;
  body.innerHTML = `<p class="small">${ctx.scene.tracks.length} vật thể, nhãn 2 lần mỗi giây.
    ${s ? `Sai số phát lại (chỉ số 1) của nhóm chuyển động: pilot ${metres(s.ade, 3)}, baseline ${metres(ctx.scene.summary.baseline?.moving?.ade, 3)}.` : "Chỉ số 1 chưa chạy cho cảnh này."}
    ${Object.keys(problems).length ? `<span class="warn-text">${Object.keys(problems).length} xe có đoạn nhãn chuyển động phi lý.</span>` : ""}</p>
    <table class="t">${header(cols, "data")}${sorted.map((r) => `<tr class="click" data-name="${escapeHtml(r.name)}" data-t="${r.problems ? r.problems[0][0] : r.start}">
      <td>${escapeHtml(r.name)}</td><td class="small">${escapeHtml(r.category)}</td><td class="num">${r.keyframes}</td>
      <td class="num">${num(r.start, 1)}–${num(r.end, 1)}</td><td>${r.stationary ? "có" : ""}</td>
      <td class="num">${r.ade != null ? num(r.ade, 3) : "–"}</td><td class="num">${r.max != null ? num(r.max, 3) : "–"}</td>
      <td class="warn-text small">${r.problems ? r.problems.map(([a, b]) => `${num(a, 1)}–${num(b, 1)} s`).join(", ") : ""}</td></tr>`).join("")}</table>`;
  for (const row of body.querySelectorAll("tr[data-name]")) {
    row.addEventListener("click", () => { ctx.select(row.dataset.name); ctx.setTime(Number(row.dataset.t)); });
  }
  bindSort(body, "data", () => tabData(ctx, body));
}

// ---------------------------------------------------------------- 7. export and provenance
function tabExport(ctx, body) {
  const out = ctx.exported, scene = ctx.scene;
  const code = scene.code || {};
  const provenance = `<dl class="kv" style="max-width:640px">
    <dt>Dữ liệu</dt><dd>${escapeHtml(ctx.source)} · ${escapeHtml(scene.name)}${scene.location ? ` · ${escapeHtml(scene.location)}` : ""}</dd>
    <dt>Code</dt><dd>${code.commit ? `${code.commit.slice(0, 10)}${code.dirty ? " (có thay đổi chưa commit)" : ""}` : "không rõ"}</dd>
    <dt>esmini</dt><dd>${escapeHtml(out?.report.esmini.version || scene.run?.esmini || "?")}</dd>
    <dt>Lưới đã xử lý tạo lúc</dt><dd>${escapeHtml(scene.run?.created || "chưa xử lý")}</dd></dl>
    <details><summary class="small">Bộ ngưỡng và tham số đang dùng</summary><div class="mono">${escapeHtml(JSON.stringify(scene.thresholds, null, 1))}</div></details>`;
  if (!out) {
    body.innerHTML = `<p class="muted">Chưa xuất. Tạo một tình huống dùng được rồi bấm <b>Tải gói kịch bản</b>. Gói gồm: file
      <code>.xosc</code> (OpenSCENARIO 1.1), file đường <code>.xodr</code>, <code>trajectories.csv</code> (mọi vật thể) và
      <code>report.json</code> (tham số, kết quả kiểm tra, độ khớp esmini, phiên bản).</p>${provenance}`;
    return;
  }
  const id = out.id;
  body.innerHTML = `<div class="two"><div>
    <ul class="small"><li><b>${escapeHtml(id)}.xosc</b>: OpenSCENARIO 1.1. Tham số sự kiện ghi trong tên file và trong report.json.</li>
      <li><b>.xodr</b>: mạng đường dựng từ bản đồ của dữ liệu.</li>
      <li><b>trajectories.csv</b>: quỹ đạo mọi vật thể, định dạng CSV của real2sim.</li>
      <li><b>report.json</b>: tham số, mô hình người lái, kết quả từng điều kiện, độ khớp esmini, phiên bản.</li></ul>
    <div class="small muted">Mở bằng esmini (sau khi giải nén):</div>
    <div class="mono">esmini --osc ${escapeHtml(id)}.xosc --window 60 60 1280 720 --fixed_timestep 0.05 --traj_filter 0</div>
    <p><a href="${out.download}">Tải lại gói (.zip)</a></p></div><div>${provenance}</div></div>`;
}

// ---------------------------------------------------------------- tables
function header(cols, key) {
  const [sortKey, dir] = ui.sort[key];
  return `<tr>${cols.map(([k, label, sortable]) => `<th class="${sortable ? "sortable" : ""}" data-sort="${sortable ? k : ""}">${label}${sortKey === k ? (dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr>`;
}

function sortRows(rows, key) {
  const [k, dir] = ui.sort[key];
  const value = (r) => (Array.isArray(r[k]) ? r[k].length : r[k]);
  return [...rows].sort((a, b) => {
    const x = value(a), y = value(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (x > y ? 1 : x < y ? -1 : 0) * dir;
  });
}

function bindSort(body, key, rerender) {
  for (const th of body.querySelectorAll("th[data-sort]")) {
    if (!th.dataset.sort) continue;
    th.addEventListener("click", () => {
      const [k, dir] = ui.sort[key];
      ui.sort[key] = [th.dataset.sort, k === th.dataset.sort ? -dir : 1];
      rerender();
    });
  }
}
