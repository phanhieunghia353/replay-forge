// Free 3D view (three.js, vendored in ../vendor): same data and public methods as the top-down
// Viewer in viewer.js, so main.js drives both the same way.
//
// Axes: world (x east, y north, z up) -> three.js (y up):  X = x,  Y = z,  Z = -y.
// Mouse (OrbitControls): left drag = rotate, right drag = pan, wheel = zoom, double click = fit.
// Rendering happens on demand (after a time, camera, layer or selection change), not in a loop.
// Variant view: as in viewer.js (actor colour, dashed ghosts, no baseline layer).
// Names are HTML labels in an overlay, moved to each object's projected roof position after every
// render (all names when the "labels" layer is on, otherwise only the selected object's).

import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";
import { ghostColour, objectColour, readColors } from "./colors.js";
import { boxCentre, poseAt, present, sceneBounds, zip } from "./geometry.js";

// Small height steps keep flat map layers from flickering into each other.
const MAP_LEVELS = [["drivable_area", 0.0], ["carpark_area", 0.01], ["walkway", 0.02], ["ped_crossing", 0.03], ["stop_line", 0.035]];
const LINE_LEVEL = 0.05;
const CLICK_SLOP_PX = 4;

export class Viewer3D {
  constructor(container, { onSelect } = {}) {
    this.container = container;
    this.onSelect = onSelect || (() => {});
    this.scene = null;
    this.time = 0;
    this.selected = null;
    this.follow = false;
    this.layers = { map: true, gt: true, pilot: true, baseline: false, labels: false };
    this.colors = readColors();
    this.objects = new Map();  // track name -> { track, pilot, gt, baseline }
    this.needsFit = true;

    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch (error) {
      this.renderer = null;
      container.textContent = "Trình duyệt này không hỗ trợ WebGL nên không hiển thị được góc nhìn 3D.";
      return;
    }
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    container.append(this.renderer.domElement);
    this.labelLayer = document.createElement("div");
    this.labelLayer.className = "labels3d";
    container.append(this.labelLayer);
    this.labels = new Map();  // track name -> label element

    this.world = new THREE.Scene();
    this.world.background = new THREE.Color(this.colors.ground);
    this.world.add(new THREE.HemisphereLight(0xffffff, 0x8a8a80, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(-60, 120, 80);
    this.world.add(sun);

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.5, 5000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05;  // stay above the ground
    this.controls.addEventListener("change", () => this.render());

    this.mapGroup = new THREE.Group();
    this.objectGroup = new THREE.Group();
    this.trailGroup = new THREE.Group();
    this.world.add(this.mapGroup, this.objectGroup, this.trailGroup);

    this._bindPicking();
    new ResizeObserver(() => this.resize()).observe(container);
  }

  // ------------------------------------------------------------------ public API (shared with Viewer)
  // keepCamera: switching between a scene and one of its variants keeps the view where it is.
  setScene(scene, keepCamera = false) {
    const sameMap = keepCamera && this.scene?.map === scene.map;
    this.scene = scene;
    this.selected = null;
    if (!this.renderer) return;
    for (const group of sameMap ? [this.objectGroup, this.trailGroup] : [this.mapGroup, this.objectGroup, this.trailGroup]) clearGroup(group);
    this.objects.clear();
    this.labelLayer.replaceChildren();
    this.labels.clear();
    if (!sameMap) this._buildMap(scene.map || {});
    for (const track of scene.tracks) this._buildObject(track);
    this.needsFit = this.needsFit || !keepCamera;
    this.resize();
  }

  setTime(t) { this.time = t; this.update(); }

  setLayer(name, on) { this.layers[name] = on; this.update(); }

  setFollow(on) { this.follow = on; this.update(); }

  // Overlays and measuring are drawn in the top-down view only.
  setOverlay() {}

  setMeasuring() {}

  // Change the selection without notifying (used to keep both viewers in sync).
  setSelected(name) {
    this.selected = name;
    this._buildTrails();
    this.update();
  }

  // Change the selection from a click: notify main.js.
  select(name) {
    this.setSelected(name);
    this.onSelect(name ? this.track(name) : null);
  }

  track(name) { return this.scene?.tracks.find((t) => t.name === name) || null; }

  fit() {
    if (!this.renderer || !this.scene) return;
    const [xmin, ymin, xmax, ymax] = sceneBounds(this.scene);
    const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
    const size = Math.max(xmax - xmin, ymax - ymin, 20);
    this.controls.target.set(cx, 0, -cy);
    this.camera.position.set(cx - 0.35 * size, 0.6 * size, -cy + 0.75 * size);  // from the south-west, above
    this.controls.update();
    this.needsFit = false;
    this.render();
  }

  // Called when the container is shown or resized.
  resize() {
    if (!this.renderer) return;
    const { clientWidth: width, clientHeight: height } = this.container;
    if (!width || !height) return;  // hidden: the top-down view is showing
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    if (this.needsFit && this.scene) this.fit();
    this.update();
  }

  // ------------------------------------------------------------------ per-frame update
  update() {
    if (!this.renderer || !this.scene) return;
    this.mapGroup.visible = this.layers.map;
    for (const { track, pilot, gt, baseline, ghost } of this.objects.values()) {
      const shown = present(track, this.time);
      const selected = track.name === this.selected;
      place(track, pilot, shown && this.layers.pilot ? poseAt(track.pilot, this.time) : null);
      place(track, gt, shown && this.layers.gt ? poseAt(track.gt, this.time) : null);
      place(track, baseline, shown && this.layers.baseline && !this.scene.variant ? poseAt(track.baseline, this.time) : null);
      if (ghost) place(track, ghost, poseAt(track.ghost, this.time));  // own time span
      pilot.material.emissive.set(selected ? this.colors.selected : 0x000000);
      pilot.material.emissiveIntensity = selected ? 0.6 : 0;
      gt.material.color.set(selected ? this.colors.selected : this.colors.gt);
    }
    this.trailGroup.visible = Boolean(this.selected);
    if (this.follow && this.selected) {
      const pose = poseAt(this.track(this.selected).gt, this.time);
      if (pose) {
        const target = new THREE.Vector3(pose.x, 0, -pose.y);
        this.camera.position.add(target.clone().sub(this.controls.target));
        this.controls.target.copy(target);
        this.controls.update();
      }
    }
    this.render();
  }

  render() {
    if (!this.renderer || !this.container.clientWidth) return;
    this.renderer.render(this.world, this.camera);
    this._placeLabels();
  }

  // Move each name label to its object's roof, projected to the screen; hide what is not shown.
  _placeLabels() {
    const { clientWidth: width, clientHeight: height } = this.container;
    const point = new THREE.Vector3();
    for (const { track, pilot, gt } of this.objects.values()) {
      const wanted = this.layers.labels || track.name === this.selected;
      const anchor = pilot.visible ? pilot : gt.visible ? gt : null;
      let label = this.labels.get(track.name);
      if (!wanted || !anchor) { if (label) label.hidden = true; continue; }
      point.set(anchor.position.x, track.size[2] + 0.4, anchor.position.z).project(this.camera);
      const onScreen = point.z > -1 && point.z < 1 && Math.abs(point.x) <= 1.05 && Math.abs(point.y) <= 1.05;
      if (!onScreen) { if (label) label.hidden = true; continue; }
      if (!label) {
        label = document.createElement("span");
        label.textContent = track.name;
        this.labelLayer.append(label);
        this.labels.set(track.name, label);
      }
      label.hidden = false;
      label.classList.toggle("selected", track.name === this.selected);
      label.style.transform = `translate(${((point.x + 1) / 2) * width}px, ${((1 - point.y) / 2) * height}px) translate(-50%, -100%)`;
    }
  }

  // ------------------------------------------------------------------ building the 3D scene
  _buildMap(map) {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(5000, 5000), new THREE.MeshLambertMaterial({ color: this.colors.ground }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.05;
    this.mapGroup.add(ground);

    const colours = { drivable_area: this.colors.drivable, carpark_area: this.colors.carpark, walkway: this.colors.walkway,
      ped_crossing: this.colors.crossing, stop_line: this.colors.stopline };
    for (const [layer, level] of MAP_LEVELS) {
      const shapes = (map[layer] || []).map(toShape);
      if (!shapes.length) continue;
      const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shapes), new THREE.MeshLambertMaterial({ color: colours[layer], side: THREE.DoubleSide }));
      mesh.rotation.x = -Math.PI / 2;  // shape plane (x, y) -> ground (X, -Z)
      mesh.position.y = level;
      this.mapGroup.add(mesh);
    }
    const dividers = [[map.road_divider || [], new THREE.LineBasicMaterial({ color: this.colors.divider })],
      [map.lane_divider || [], new THREE.LineDashedMaterial({ color: this.colors.divider, dashSize: 3, gapSize: 3 })]];
    for (const [lines, material] of dividers) {
      for (const points of lines) {
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points.map(([x, y]) => new THREE.Vector3(x, LINE_LEVEL, -y))), material);
        line.computeLineDistances();
        this.mapGroup.add(line);
      }
    }
  }

  _buildObject(track) {
    const [length, width, height] = track.size;
    const box = new THREE.BoxGeometry(length, height, width);  // X = length, Y = height, Z = width
    const edges = new THREE.EdgesGeometry(box);
    const pilot = new THREE.Mesh(box, new THREE.MeshLambertMaterial({ color: objectColour(this.colors, track), transparent: true, opacity: 0.9 }));
    const gt = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: this.colors.gt }));
    const baseline = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: this.colors.baseline }));
    pilot.userData.name = track.name;
    this.objectGroup.add(pilot, gt, baseline);
    let ghost = null;
    if (track.ghost) {  // variant view: dashed outline of where the object would be
      ghost = new THREE.LineSegments(edges, new THREE.LineDashedMaterial({ color: ghostColour(this.colors, track), dashSize: 0.4, gapSize: 0.3 }));
      ghost.computeLineDistances();
      this.objectGroup.add(ghost);
    }
    this.objects.set(track.name, { track, pilot, gt, baseline, ghost });
  }

  _buildTrails() {
    if (!this.renderer) return;
    clearGroup(this.trailGroup);
    const track = this.selected && this.track(this.selected);
    if (!track) return;
    const lift = (points) => points.map(([x, y]) => new THREE.Vector3(x, 0.15, -y));
    const path = new THREE.Line(new THREE.BufferGeometry().setFromPoints(lift(zip(track.pilot))),
      new THREE.LineBasicMaterial({ color: objectColour(this.colors, track) }));
    const dots = new THREE.Points(new THREE.BufferGeometry().setFromPoints(lift(zip(track.gt))),
      new THREE.PointsMaterial({ color: this.colors.gt, size: 6, sizeAttenuation: false }));
    this.trailGroup.add(path, dots);
  }

  // ------------------------------------------------------------------ mouse picking
  _bindPicking() {
    const canvas = this.renderer.domElement;
    const raycaster = new THREE.Raycaster();
    let down = null;
    canvas.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
    canvas.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > CLICK_SLOP_PX || e.button !== 0) { down = null; return; }
      down = null;
      const rect = canvas.getBoundingClientRect();
      const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(ndc, this.camera);
      const meshes = [...this.objects.values()].map((o) => o.pilot).filter((m) => m.visible);
      const hit = raycaster.intersectObjects(meshes, false)[0];
      this.select(hit ? hit.object.userData.name : null);
    });
    canvas.addEventListener("dblclick", () => this.fit());
  }
}

// -------------------------------------------------------------------- helpers
function place(track, object, pose) {
  object.visible = Boolean(pose);
  if (!pose) return;
  const [cx, cy] = boxCentre(track, pose);
  object.position.set(cx, track.size[2] / 2, -cy);
  object.rotation.y = pose.yaw;
}

function toShape(polygon) {
  const shape = new THREE.Shape(polygon.ext.map(([x, y]) => new THREE.Vector2(x, y)));
  for (const hole of polygon.holes) shape.holes.push(new THREE.Path(hole.map(([x, y]) => new THREE.Vector2(x, y))));
  return shape;
}

function clearGroup(group) {
  for (const child of [...group.children]) {
    group.remove(child);
    child.geometry?.dispose();
    child.material?.dispose();
  }
}
