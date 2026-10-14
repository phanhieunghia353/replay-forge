// Small line charts on a <canvas> (no library): several series over time, dashed series for the
// recording, horizontal threshold lines, and a vertical line at the current time. A click reports the time.

import { num } from "./format.js";

const PAD = { left: 44, right: 12, top: 18, bottom: 22 };

// spec: {t: [...], series: [{values, colour, dash, label}], now, thresholds: [{value, label, colour}],
//        unit, yMin, yMax}
export function drawChart(canvas, spec) {
  const ratio = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (!width || !height) return;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const css = getComputedStyle(document.documentElement);
  const muted = css.getPropertyValue("--muted").trim(), grid = css.getPropertyValue("--border").trim();
  const { t } = spec;
  if (!t?.length) return;

  let lo = spec.yMin ?? Infinity, hi = spec.yMax ?? -Infinity;
  for (const s of spec.series) for (const v of s.values) if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  for (const th of spec.thresholds || []) { lo = Math.min(lo, th.value); hi = Math.max(hi, th.value); }
  if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
  if (hi - lo < 1e-6) hi = lo + 1;
  const pad = 0.06 * (hi - lo);
  lo = spec.yMin ?? lo - pad; hi = spec.yMax ?? hi + pad;
  const t0 = t[0], t1 = t[t.length - 1];
  const X = (v) => PAD.left + ((v - t0) / (t1 - t0 || 1)) * (width - PAD.left - PAD.right);
  const Y = (v) => height - PAD.bottom - ((v - lo) / (hi - lo)) * (height - PAD.top - PAD.bottom);

  ctx.font = "11px Segoe UI, sans-serif";
  ctx.strokeStyle = grid; ctx.fillStyle = muted; ctx.lineWidth = 1;
  for (let k = 0; k <= 4; k++) {  // horizontal grid with values
    const v = lo + (k / 4) * (hi - lo), y = Y(v);
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(width - PAD.right, y); ctx.stroke();
    ctx.fillText(num(v, Math.abs(hi - lo) < 5 ? 1 : 0), 4, y + 4);
  }
  const step = Math.max(1, Math.round((t1 - t0) / 10));
  for (let v = Math.ceil(t0); v <= t1; v += step) ctx.fillText(`${v}`, X(v) - 3, height - 6);
  ctx.fillText(spec.unit || "", 4, 11);
  ctx.fillText("t (s)", width - PAD.right - 26, height - 6);

  for (const th of spec.thresholds || []) {
    ctx.setLineDash([5, 4]); ctx.strokeStyle = th.colour || muted;
    ctx.beginPath(); ctx.moveTo(PAD.left, Y(th.value)); ctx.lineTo(width - PAD.right, Y(th.value)); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = th.colour || muted;
    ctx.fillText(th.label, width - PAD.right - ctx.measureText(th.label).width - 2, Y(th.value) - 3);
  }
  for (const s of spec.series) {
    ctx.beginPath();
    let open = false;
    s.values.forEach((v, i) => {
      if (v == null) { open = false; return; }
      if (open) ctx.lineTo(X(t[i]), Y(v)); else { ctx.moveTo(X(t[i]), Y(v)); open = true; }
    });
    ctx.setLineDash(s.dash ? [5, 4] : []); ctx.lineWidth = s.dash ? 1.2 : 2; ctx.strokeStyle = s.colour; ctx.stroke();
    ctx.setLineDash([]);
  }
  if (spec.now != null) {
    ctx.strokeStyle = css.getPropertyValue("--obj-selected").trim(); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(X(spec.now), PAD.top - 6); ctx.lineTo(X(spec.now), height - PAD.bottom); ctx.stroke();
  }
  let x = PAD.left + 4;  // legend
  for (const s of spec.series.filter((s) => s.label)) {
    ctx.fillStyle = s.colour; ctx.fillRect(x, 4, 12, 3);
    ctx.fillStyle = muted; ctx.fillText(s.label, x + 16, 10);
    x += 24 + ctx.measureText(s.label).width;
  }
  canvas._toTime = (px) => t0 + ((px - PAD.left) / (width - PAD.left - PAD.right)) * (t1 - t0);
}

// Clicking the chart moves the timeline there.
export function onChartClick(canvas, onTime) {
  canvas.addEventListener("click", (e) => {
    if (canvas._toTime) onTime(Math.max(0, canvas._toTime(e.offsetX)));
  });
}
