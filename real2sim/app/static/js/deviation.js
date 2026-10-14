// How far the reconstructions (pilot, baseline) are from the real object (gt) at a given time, and
// a small chart of that distance over the object's whole time span.
//
// Between two annotation keyframes the real position is the straight-line interpolation of the
// labels (the same rule the replay error uses at keyframe times).

import { poseAt } from "./geometry.js";

const STEP_S = 0.1;

// {distance, along, lateral} in metres, or null when the object is not present at time t.
// along > 0: the reconstruction is ahead of the real object along its heading; lateral > 0: to its left.
export function deviationAt(track, method, t) {
  const real = poseAt(track.gt, t);
  const sim = poseAt(track[method], t);
  if (!real || !sim) return null;
  const dx = sim.x - real.x, dy = sim.y - real.y;
  const c = Math.cos(real.yaw), s = Math.sin(real.yaw);
  return { distance: Math.hypot(dx, dy), along: dx * c + dy * s, lateral: -dx * s + dy * c };
}

// Distance over time for each method: {t: [...], pilot: [...], baseline: [...]}.
export function deviationSeries(track, methods = ["pilot", "baseline"]) {
  const times = track.gt.t;
  const series = { t: [] };
  for (const method of methods) series[method] = [];
  for (let t = times[0]; t <= times[times.length - 1] + 1e-9; t += STEP_S) {
    series.t.push(t);
    for (const method of methods) series[method].push(deviationAt(track, method, t)?.distance ?? null);
  }
  return series;
}

// Line chart of the series on a <canvas>, with a vertical marker at time `now`.
export function drawDeviationChart(canvas, series, now, colours) {
  const ratio = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (!width || !height || series.t.length < 2) return;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = { left: 34, right: 6, top: 6, bottom: 16 };
  const t0 = series.t[0], t1 = series.t[series.t.length - 1];
  const values = ["pilot", "baseline"].flatMap((m) => (series[m] || []).filter((v) => v != null));
  const top = Math.max(0.5, ...values) * 1.1;
  const x = (t) => pad.left + ((t - t0) / Math.max(t1 - t0, 1e-6)) * (width - pad.left - pad.right);
  const y = (v) => height - pad.bottom - (v / top) * (height - pad.top - pad.bottom);

  ctx.strokeStyle = colours.grid;
  ctx.fillStyle = colours.text;
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.lineWidth = 1;
  for (const v of [0, top / 2, top]) {
    ctx.beginPath(); ctx.moveTo(pad.left, y(v)); ctx.lineTo(width - pad.right, y(v)); ctx.stroke();
    ctx.fillText(`${v.toFixed(v < 1 ? 2 : 1).replace(".", ",")} m`, 0, y(v) + 4);
  }
  ctx.fillText(`${t0.toFixed(1).replace(".", ",")} s`, pad.left, height - 2);
  const endLabel = `${t1.toFixed(1).replace(".", ",")} s`;
  ctx.fillText(endLabel, width - pad.right - ctx.measureText(endLabel).width, height - 2);

  for (const [method, colour, dash] of [["baseline", colours.baseline, [4, 3]], ["pilot", colours.pilot, []]]) {
    const values = series[method];
    if (!values) continue;
    ctx.beginPath();
    let drawing = false;
    values.forEach((v, i) => {
      if (v == null) { drawing = false; return; }
      drawing ? ctx.lineTo(x(series.t[i]), y(v)) : ctx.moveTo(x(series.t[i]), y(v));
      drawing = true;
    });
    ctx.setLineDash(dash); ctx.strokeStyle = colour; ctx.lineWidth = 2; ctx.stroke(); ctx.setLineDash([]);
  }

  if (now >= t0 && now <= t1) {
    ctx.strokeStyle = colours.now; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x(now), pad.top); ctx.lineTo(x(now), height - pad.bottom); ctx.stroke();
  }
}
