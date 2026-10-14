// Top-down viewer: draws the map and every object at the current time on a <canvas>.
//
// World frame: metres, x east, y north (scene-local, same as the server).
// Screen frame: CSS pixels, y down. camera = world point at the canvas centre + pixels per metre.
//
// Layers per object (each can be toggled):
//   gt        raw annotation boxes (outline)            -> what really happened
//   pilot     careful reconstruction (filled)            -> what the scenario replays
//   baseline  coarse reconstruction (dashed outline)
// An object is only drawn while it is annotated (inside its gt time span).
//
// Variant view (scene.variant set, built by main.js): the "pilot" poses of each track are what the
// variant replays, the braking vehicle and the reacting ones are drawn in their own colours, and a track
// may carry a dashed "ghost" (where it was in the recording).
//
// Overlays (setOverlay, built by main.js for the current time): dashed outlines of the vehicles the user
// may make brake, "follows" arrows, text tags next to objects, a highlighted path, and a measuring tool.
//
// Same public methods as Viewer3D (viewer3d.js), so main.js can drive either one.
//
// Speed: the map (thousands of points) is turned into Path2D shapes once per scene, in metres.
// Each frame only sets one canvas transform (world -> screen) and refills those shapes, so the
// browser does the per-point work. Mouse moves and wheel steps are coalesced to one draw per frame.

import { ghostColour, objectColour, readColors } from "./colors.js";
import { num } from "./format.js";
import { boxCentre, boxCorners, poseAt, present, sceneBounds, zip } from "./geometry.js";

const ZOOM_STEP = 1.15;
const CLICK_SLOP_PX = 4;

export class Viewer {
  constructor(canvas, { onSelect } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onSelect = onSelect || (() => {});
    this.scene = null;
    this.time = 0;
    this.selected = null;
    this.follow = false;
    this.layers = { map: true, gt: true, pilot: true, baseline: false, labels: false, ghosts: true, stoplines: true };
    this.overlay = null;    // {pick: Set, arrows: [[from, to]], tags: [{name, text, colour}], path: [[x, y]]}
    this.measuring = false;
    this.measurePoints = [];
    this.camera = { x: 0, y: 0, scale: 4 };
    this.colors = readColors();
    this.size = { width: 0, height: 0 };  // CSS pixels, refreshed once per draw
    this.mapPaths = null;                 // Path2D shapes in metres, built once per scene
    this._drawPending = false;
    this._bindEvents();
    new ResizeObserver(() => this.requestDraw()).observe(canvas);
  }

  // ------------------------------------------------------------------ public API (shared with Viewer3D)
  // keepCamera: switching between a scene and one of its variants keeps the view where it is.
  setScene(scene, keepCamera = false) {
    this.scene = scene;
    this.selected = null;
    this.mapPaths = buildMapPaths(scene.map || {});
    if (keepCamera) this.requestDraw(); else this.fit();
  }

  setTime(t) { this.time = t; this.requestDraw(); }

  setLayer(name, on) { this.layers[name] = on; this.requestDraw(); }

  setFollow(on) { this.follow = on; this.requestDraw(); }

  setOverlay(overlay) { this.overlay = overlay; this.requestDraw(); }

  // Measuring: clicks place two points (a third starts again) instead of selecting objects.
  setMeasuring(on) {
    this.measuring = on;
    this.measurePoints = [];
    this.canvas.classList.toggle("measuring", on);
    this.requestDraw();
  }

  // Change the selection without notifying (used to keep both viewers in sync).
  setSelected(name) { this.selected = name; this.requestDraw(); }

  // Draw at the next animation frame; several requests in one frame give one draw.
  requestDraw() {
    if (this._drawPending) return;
    this._drawPending = true;
    requestAnimationFrame(() => { this._drawPending = false; this.draw(); });
  }

  // Change the selection from a click: notify main.js.
  select(name) {
    this.setSelected(name);
    this.onSelect(name ? this.track(name) : null);
  }

  track(name) { return this.scene?.tracks.find((t) => t.name === name) || null; }

  // While the canvas is hidden (3D view showing) it has no size: fit at the next draw instead, or the
  // scale would become 0 and the view stay broken after switching back.
  // focus: [xmin, ymin, xmax, ymax] to frame instead of the whole scene (kept for later fits).
  fit(focus = undefined) {
    if (focus !== undefined) this.focus = focus;
    if (!this.scene) return;
    const { width, height } = this.canvas.getBoundingClientRect();
    if (!width || !height) { this.needsFit = true; return; }
    this.needsFit = false;
    const [xmin, ymin, xmax, ymax] = this.focus || sceneBounds(this.scene);
    this.camera.x = (xmin + xmax) / 2;
    this.camera.y = (ymin + ymax) / 2;
    this.camera.scale = 0.9 * Math.min(width / Math.max(xmax - xmin, 10), height / Math.max(ymax - ymin, 10));
    this.requestDraw();
  }

  // ------------------------------------------------------------------ drawing
  draw() {
    const { ctx, canvas } = this;
    const ratio = window.devicePixelRatio || 1;
    const { width, height } = canvas.getBoundingClientRect();  // the only layout query per frame
    this.size = { width, height };
    if (!width || !height) return;  // hidden (the 3D view is showing)
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    if (this.needsFit) this.fit();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = this.colors.ground;
    ctx.fillRect(0, 0, width, height);
    if (!this.scene) return;

    if (this.follow && this.selected) {
      const pose = poseAt(this.track(this.selected).gt, this.time);
      if (pose) { this.camera.x = pose.x; this.camera.y = pose.y; }
    }
    if (this.layers.map && this.mapPaths) this._drawMap(ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    if (this.overlay?.path?.length) this._polyline(this.overlay.path, this.colors.selected, 6, [], 0.35);
    if (this.selected) this._drawTrails(this.track(this.selected));
    for (const track of this.scene.tracks) this._drawTrack(track);
    if (this.overlay) this._drawOverlay(this.overlay);
    if (this.measurePoints.length) this._drawMeasure();
  }

  _poseOf(name) {
    const track = this.track(name);
    if (!track || !present(track, this.time)) return null;
    const pose = poseAt(track.pilot, this.time) || poseAt(track.gt, this.time);
    return pose ? { track, pose } : null;
  }

  _drawOverlay({ pick, arrows, tags }) {
    const ctx = this.ctx;
    for (const name of pick || []) {
      const found = this._poseOf(name);
      if (found) this._box(found.track, found.pose, { stroke: this.colors.pick, dash: [4, 3], width: 2.5, grow: 0.6 });
    }
    for (const [from, to] of arrows || []) {
      const a = this._poseOf(from), b = this._poseOf(to);
      if (!a || !b) continue;
      const [ax, ay] = this.toScreen(...boxCentre(a.track, a.pose));
      const [bx, by] = this.toScreen(...boxCentre(b.track, b.pose));
      const mx = (ax + bx) / 2 - (by - ay) * 0.25, my = (ay + by) / 2 + (bx - ax) * 0.25;  // a gentle curve
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.quadraticCurveTo(mx, my, bx, by);
      ctx.lineWidth = 1.5; ctx.strokeStyle = this.colors.leader; ctx.stroke();
      const angle = Math.atan2(by - my, bx - mx);
      ctx.beginPath(); ctx.moveTo(bx, by);
      ctx.lineTo(bx - 8 * Math.cos(angle - 0.4), by - 8 * Math.sin(angle - 0.4));
      ctx.lineTo(bx - 8 * Math.cos(angle + 0.4), by - 8 * Math.sin(angle + 0.4));
      ctx.closePath(); ctx.fillStyle = this.colors.leader; ctx.fill();
    }
    ctx.font = "12px Segoe UI, sans-serif";
    for (const { name, text, colour } of tags || []) {
      const found = this._poseOf(name);
      if (!found) continue;
      const [px, py] = this.toScreen(...boxCentre(found.track, found.pose));
      const width = ctx.measureText(text).width + 8;
      ctx.fillStyle = "rgba(255,255,255,0.9)"; ctx.fillRect(px - width / 2, py + 10, width, 16);
      ctx.fillStyle = colour || this.colors.gt; ctx.fillText(text, px - width / 2 + 4, py + 22);
    }
  }

  _drawMeasure() {
    const ctx = this.ctx;
    const pts = this.measurePoints.map(([x, y]) => this.toScreen(x, y));
    ctx.fillStyle = this.colors.gt;
    for (const [px, py] of pts) { ctx.beginPath(); ctx.arc(px, py, 4, 0, 2 * Math.PI); ctx.fill(); }
    if (pts.length === 2) {
      ctx.beginPath(); ctx.moveTo(...pts[0]); ctx.lineTo(...pts[1]);
      ctx.setLineDash([6, 4]); ctx.lineWidth = 2; ctx.strokeStyle = this.colors.gt; ctx.stroke(); ctx.setLineDash([]);
      const [[x0, y0], [x1, y1]] = this.measurePoints;
      const text = `${num(Math.hypot(x1 - x0, y1 - y0), 2)} m`;
      ctx.font = "bold 13px Segoe UI, sans-serif";
      const mx = (pts[0][0] + pts[1][0]) / 2, my = (pts[0][1] + pts[1][1]) / 2;
      const width = ctx.measureText(text).width + 10;
      ctx.fillStyle = "rgba(255,255,255,0.95)"; ctx.fillRect(mx - width / 2, my - 22, width, 18);
      ctx.fillStyle = this.colors.gt; ctx.fillText(text, mx - width / 2 + 5, my - 8);
    }
  }

  // Map shapes are in metres: one transform maps them to the screen (y flipped: north is up).
  _drawMap(ratio) {
    const { ctx, colors: c, mapPaths: paths } = this;
    const { x, y, scale } = this.camera;
    const { width, height } = this.size;
    ctx.setTransform(ratio * scale, 0, 0, -ratio * scale, ratio * (width / 2 - x * scale), ratio * (height / 2 + y * scale));
    const px = 1 / scale;  // one screen pixel in metres, for line widths and dashes
    for (const [layer, colour] of [["drivable_area", c.drivable], ["carpark_area", c.carpark], ["walkway", c.walkway],
      ["ped_crossing", c.crossing]]) {
      if (paths[layer]) { ctx.fillStyle = colour; ctx.fill(paths[layer], "evenodd"); }
    }
    if (paths.stop_line && this.layers.stoplines) { ctx.fillStyle = c.stopline; ctx.fill(paths.stop_line, "evenodd"); }
    ctx.strokeStyle = c.laneEdge;
    ctx.lineWidth = 0.5 * px;
    if (paths.laneEdges) ctx.stroke(paths.laneEdges);
    ctx.strokeStyle = c.divider;
    ctx.lineWidth = 1.5 * px;
    if (paths.road_divider) ctx.stroke(paths.road_divider);
    ctx.lineWidth = px;
    ctx.setLineDash([6 * px, 6 * px]);
    if (paths.lane_divider) ctx.stroke(paths.lane_divider);
    ctx.setLineDash([]);
  }

  _drawTrails(track) {
    if (!track) return;
    this._polyline(zip(track.pilot), objectColour(this.colors, track), 2, []);
    if (this.layers.baseline && !this.scene.variant) this._polyline(zip(track.baseline), this.colors.baseline, 1.5, [4, 4]);
    if (track.actor || track.reacted) return;  // simulated motion: there are no label keyframes to mark
    this.ctx.fillStyle = this.colors.gt;
    for (let i = 0; i < track.gt.x.length; i++) {
      const [px, py] = this.toScreen(track.gt.x[i], track.gt.y[i]);
      this.ctx.beginPath();
      this.ctx.arc(px, py, 2.5, 0, 2 * Math.PI);
      this.ctx.fill();
    }
  }

  _drawTrack(track) {
    if (track.ghost && this.layers.ghosts) {  // variant view: dashed "where it was" outline (own time span)
      const pose = poseAt(track.ghost, this.time);
      if (pose) this._box(track, pose, { stroke: ghostColour(this.colors, track), dash: [5, 4], width: 2 });
    }
    if (!present(track, this.time)) return;
    const selected = track.name === this.selected;
    const colour = objectColour(this.colors, track);
    if (this.layers.baseline && !this.scene.variant) {
      const pose = poseAt(track.baseline, this.time);
      if (pose) this._box(track, pose, { stroke: this.colors.baseline, dash: [4, 3], width: 1.5 });
    }
    if (this.layers.pilot) {
      const pose = poseAt(track.pilot, this.time);
      if (pose) this._box(track, pose, { fill: colour, stroke: selected ? this.colors.selected : colour, width: selected ? 3 : 1, nose: true });
    }
    if (this.layers.gt) {
      const pose = poseAt(track.gt, this.time);
      if (pose) this._box(track, pose, { stroke: selected ? this.colors.selected : this.colors.gt, width: selected ? 2.5 : 1 });
    }
    if (this.layers.labels || selected) {
      const pose = poseAt(track.pilot, this.time) || poseAt(track.gt, this.time);
      if (pose) {
        const [px, py] = this.toScreen(pose.x, pose.y);
        this.ctx.font = "12px Segoe UI, sans-serif";
        this.ctx.fillStyle = this.colors.gt;
        this.ctx.fillText(track.name, px + 8, py - 8);
      }
    }
  }

  // ------------------------------------------------------------------ primitives
  // Uses the canvas size measured at the last draw (no layout query per point).
  toScreen(x, y) {
    const { width, height } = this.size;
    return [(x - this.camera.x) * this.camera.scale + width / 2, height / 2 - (y - this.camera.y) * this.camera.scale];
  }

  toWorld(px, py) {
    const { width, height } = this.size;
    return [(px - width / 2) / this.camera.scale + this.camera.x, (height / 2 - py) / this.camera.scale + this.camera.y];
  }

  _box(track, pose, { fill = null, stroke = null, width = 1, dash = [], nose = false, grow = 0 }) {
    const sized = grow ? { ...track, size: [track.size[0] + 2 * grow, track.size[1] + 2 * grow, track.size[2]] } : track;
    const corners = boxCorners(sized, pose).map(([x, y]) => this.toScreen(x, y));
    const ctx = this.ctx;
    ctx.beginPath();
    corners.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.closePath();
    if (fill) { ctx.globalAlpha = 0.75; ctx.fillStyle = fill; ctx.fill(); ctx.globalAlpha = 1; }
    if (stroke) { ctx.setLineDash(dash); ctx.lineWidth = width; ctx.strokeStyle = stroke; ctx.stroke(); ctx.setLineDash([]); }
    if (nose) {  // white line on the front edge shows the heading
      const [a, b] = [corners[1], corners[2]];
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
      ctx.lineWidth = 2; ctx.strokeStyle = "#ffffff"; ctx.stroke();
    }
  }

  _polyline(points, colour, width, dash, alpha = 1) {
    const ctx = this.ctx;
    ctx.beginPath();
    points.forEach(([x, y], i) => { const [px, py] = this.toScreen(x, y); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    ctx.globalAlpha = alpha; ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.setLineDash(dash); ctx.lineWidth = width; ctx.strokeStyle = colour; ctx.stroke(); ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ mouse
  _bindEvents() {
    const canvas = this.canvas;
    let drag = null;
    canvas.addEventListener("mousedown", (e) => {
      drag = { x: e.offsetX, y: e.offsetY, cx: this.camera.x, cy: this.camera.y, moved: false };
      canvas.classList.add("dragging");
    });
    window.addEventListener("mousemove", (e) => {
      if (!drag) return;
      const rect = canvas.getBoundingClientRect();
      const dx = e.clientX - rect.left - drag.x, dy = e.clientY - rect.top - drag.y;
      if (Math.hypot(dx, dy) > CLICK_SLOP_PX) drag.moved = true;
      if (drag.moved) {
        this.camera.x = drag.cx - dx / this.camera.scale;
        this.camera.y = drag.cy + dy / this.camera.scale;
        this.requestDraw();
      }
    });
    window.addEventListener("mouseup", (e) => {
      if (!drag) return;
      canvas.classList.remove("dragging");
      if (!drag.moved && e.target === canvas) {
        if (this.measuring) {
          if (this.measurePoints.length >= 2) this.measurePoints = [];
          this.measurePoints.push(this.toWorld(e.offsetX, e.offsetY));
          this.requestDraw();
        } else this.select(this._hit(e.offsetX, e.offsetY));
      }
      drag = null;
    });
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const [wx, wy] = this.toWorld(e.offsetX, e.offsetY);
      this.camera.scale *= e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      const [nx, ny] = this.toWorld(e.offsetX, e.offsetY);
      this.camera.x += wx - nx;
      this.camera.y += wy - ny;
      this.requestDraw();
    }, { passive: false });
    canvas.addEventListener("dblclick", () => this.fit());
  }

  _hit(px, py) {
    if (!this.scene) return null;
    const [x, y] = this.toWorld(px, py);
    const margin = 6 / this.camera.scale;  // a few pixels of slack for small objects
    let best = null;
    for (const track of this.scene.tracks) {
      if (!present(track, this.time)) continue;
      const pose = poseAt(track.pilot, this.time) || poseAt(track.gt, this.time);
      if (!pose) continue;
      const [cx, cy] = boxCentre(track, pose);
      const c = Math.cos(-pose.yaw), s = Math.sin(-pose.yaw);
      const lx = (x - cx) * c - (y - cy) * s, ly = (x - cx) * s + (y - cy) * c;
      const [length, width] = track.size;
      if (Math.abs(lx) <= length / 2 + margin && Math.abs(ly) <= width / 2 + margin) {
        const area = length * width;
        if (!best || area < best.area) best = { name: track.name, area };  // prefer the smaller object
      }
    }
    return best ? best.name : null;
  }
}

// One Path2D per map layer, in metres (scene frame). Filled layers keep holes (even-odd rule);
// lane and lane-connector outlines are merged into one stroked path.
function buildMapPaths(map) {
  const ring = (path, points) => {
    points.forEach(([x, y], i) => (i ? path.lineTo(x, y) : path.moveTo(x, y)));
    path.closePath();
  };
  const paths = {};
  for (const layer of ["drivable_area", "carpark_area", "walkway", "ped_crossing", "stop_line"]) {
    if (!map[layer]?.length) continue;
    const path = new Path2D();
    for (const polygon of map[layer]) { ring(path, polygon.ext); polygon.holes.forEach((hole) => ring(path, hole)); }
    paths[layer] = path;
  }
  const edges = new Path2D();
  for (const layer of ["lane", "lane_connector"]) for (const polygon of map[layer] || []) ring(edges, polygon.ext);
  paths.laneEdges = edges;
  for (const layer of ["road_divider", "lane_divider"]) {
    if (!map[layer]?.length) continue;
    const path = new Path2D();
    for (const line of map[layer]) line.forEach(([x, y], i) => (i ? path.lineTo(x, y) : path.moveTo(x, y)));
    paths[layer] = path;
  }
  return paths;
}
