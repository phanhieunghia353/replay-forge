"""JSON-ready data for the web app, built with the same code as the command line.

Everything returned here is plain dicts/lists of numbers and strings, in each scene's local frame
(metres, x east, y north). The browser never reads dataset files itself.

Workspace(data_dir, out_root)    one per server
  .status()                      esmini found?, sources
  .sources()                     data sources (registry.py), with scene counts or load errors
  .add_nuscenes(...) / .add_csv(...) / .remove_source(id)
  .scene_list(source)            sidebar rows: scene, description, processed numbers
  .scene(source, name)           viewer: map layers, tracks (gt / baseline / pilot), metrics, variants
                                 (stage 1 events: summary and every valid variant, per method)
  .variant(source, name, method, id)  one variant of the processed grid: the vehicles it changes
  .simulate_event(source, name, params)  a user-made scenario: trajectories, states, series, checks
  .export_event(source, name, params)    the same, replayed in esmini, as a .zip of files
  .download(source, name, id)            path of an exported .zip
  .process(source, scenes)       queue processing jobs (jobs.py -> pipeline.process_scene)
  .jobs()                        job list with progress
"""

from __future__ import annotations

import json
import math
import re
import shutil
import threading
from pathlib import Path

import numpy as np

from real2sim import behavior, events
from real2sim.abstraction import reconstruct
from real2sim.app.jobs import Job, JobRunner
from real2sim.app.registry import Registry
from real2sim.esmini import find_esmini
from real2sim.pipeline import PipelineError, code_version, export_event, process_scene, scene_dir
from real2sim.sources import Source, SourceError, load_source
from real2sim.tracks import Track
from real2sim.xodr import scene_box

VIEW_MARGIN = 40.0  # m of map around the scene's tracks
METHODS = ("exact", "baseline", "pilot")


def _round(values, digits: int) -> list:
    return np.round(np.asarray(values, float), digits).tolist()


def track_poses(track: Track) -> dict:
    return {"t": _round(track.t, 3), "x": _round(track.xy[:, 0], 3), "y": _round(track.xy[:, 1], 3),
            "yaw": _round(track.yaw, 4)}


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


SERIES_STEP = 2  # grid steps (0.1 s) between points sent for drawing
TARGET_LABEL = {"stop": "dừng", "half": "chậm lại còn nửa tốc độ"}


def _segments(t: np.ndarray, values) -> list:
    """Runs of equal values as [start time, end time, value]."""
    out = []
    for k, value in enumerate(values):
        if out and out[-1][2] == value:
            out[-1][1] = round(float(t[k]), 2)
        else:
            out.append([round(float(t[k]), 2), round(float(t[k]), 2), value])
    return out


def _series(values: np.ndarray, digits: int = 2) -> list:
    return [None if not math.isfinite(v) else round(float(v), digits) for v in values]


def _case(row: dict) -> dict:
    """What the side panel lists for one stage-1 variant (a row of events/<method>/report.json)."""
    ego = row.get("ego") or {}
    return {key: row.get(key) for key in ("id", "encounter", "actor", "t0", "decel", "target", "dwell", "group",
                                          "valid", "reasons", "reacted", "kept", "max_decel_used")} | {
        "a_used": ego.get("a_used"), "a_min": ego.get("a_min"), "min_gap": ego.get("min_gap"),
        "min_ttc": ego.get("min_ttc"), "recorded_min_gap": ego.get("recorded_min_gap")}


class Workspace:
    def __init__(self, data_dir: str | Path, out_root: str | Path, esmini: str | None = None):
        self.registry = Registry(data_dir, out_root)
        self.out_root = Path(out_root)
        self.esmini = esmini
        self._sources: dict[str, Source] = {}
        self._errors: dict[str, str] = {}
        self._scenes: dict[tuple[str, str], dict] = {}
        self._models: dict[tuple[str, str], behavior.SceneModel] = {}
        self._lock = threading.Lock()
        self.runner = JobRunner(self._run_job, self._job_done)

    # ------------------------------------------------------------------ sources
    def source(self, source_id: str) -> Source:
        with self._lock:
            if source_id in self._sources:
                return self._sources[source_id]
        entry = self.registry.entry(source_id)
        if entry is None:
            raise SourceError(f"Không có nguồn dữ liệu '{source_id}'.")
        source = load_source(entry)
        with self._lock:
            self._sources[source_id] = source
        return source

    def sources(self) -> list[dict]:
        rows = []
        for entry in self.registry.entries():
            row = {"id": entry["id"], "label": entry.get("label", entry["id"]), "kind": entry["kind"]}
            try:
                row["scenes"] = len(self.source(entry["id"]).scene_names())
            except Exception as exc:  # broken path, edited CSV, …: show it, do not crash the list
                row["error"] = str(exc)
            rows.append(row)
        return rows

    def add_nuscenes(self, dataroot: str, version: str, label: str = "") -> dict:
        return self.registry.add_nuscenes(dataroot, version, label)

    def add_csv(self, label: str, csv_text: str, xodr: dict[str, str] | None = None) -> dict:
        return self.registry.add_csv(label, csv_text, xodr)

    def remove_source(self, source_id: str) -> None:
        self.registry.remove(source_id)
        with self._lock:
            self._sources.pop(source_id, None)
            self._scenes = {k: v for k, v in self._scenes.items() if k[0] != source_id}
            self._models = {k: v for k, v in self._models.items() if k[0] != source_id}

    def status(self) -> dict:
        exe = find_esmini(self.esmini)
        return {"esmini": str(exe) if exe else None, "sources": len(self.registry.entries())}

    # ------------------------------------------------------------------ sidebar
    def scene_list(self, source_id: str) -> list[dict]:
        source = self.source(source_id)
        rows = []
        for name in source.scene_names():
            folder = scene_dir(self.out_root, source, name)
            pilot = _read_json(folder / "pilot" / "metrics.json")
            report = _read_json(folder / "events" / "pilot" / "report.json")
            summary = report["summary"] if report else None
            rows.append({
                "name": name,
                "description": source.description(name),
                "location": source.location(name),
                "processed": bool(pilot and report),
                "pilot_ade_moving": pilot["summary"].get("moving", {}).get("ade") if pilot else None,
                "valid": summary["valid"] if summary else None,
                "written": summary["attempted"] if summary else None,
                "rare": summary["valuable"] if summary else None,
            })
        return rows

    # ------------------------------------------------------------------ one variant
    def model(self, source_id: str, name: str) -> behavior.SceneModel:
        key = (source_id, name)
        with self._lock:
            cached = self._models.get(key)
        if cached is None:
            cached = behavior.SceneModel(self.source(source_id).scene(name))
            with self._lock:
                self._models[key] = cached
        return cached

    def variant(self, source_id: str, name: str, method: str, variant_id: str) -> dict:
        """Every vehicle one stage-1 variant changes (the event vehicle, and in the pilot those that react),
        on its changed trajectory, simulated again with the same code that wrote the report."""
        if method not in ("baseline", "pilot"):
            raise SourceError(f"Cách dựng không hợp lệ: {method!r}")
        source = self.source(source_id)
        report = _read_json(scene_dir(self.out_root, source, name) / "events" / method / "report.json")
        row = next((v for v in (report or {}).get("variants", []) if v["id"] == variant_id), None)
        if row is None:
            raise SourceError(f"Không có biến thể '{variant_id}' trong kết quả của {name} ({method}).")
        model = self.model(source_id, name)
        event = behavior.Event(row["actor"], row["t0"], row["decel"], row["target"], row["dwell"])
        out = behavior.simulate(model, event, react=method == "pilot")
        changed = {}
        for i in np.flatnonzero(out.changed):
            t, ref, heading = behavior.poses(model, out, i)
            keep = slice(None, None, 2)  # 0.1 s is plenty for drawing
            name_i = model.agents[i].name
            changed[name_i] = {"role": "event" if name_i == event.actor else "reacted",
                               "poses": {"t": _round(t[keep], 3), "x": _round(ref[keep, 0], 3),
                                         "y": _round(ref[keep, 1], 3), "yaw": _round(heading[keep], 4)}}
        return {"method": method, "case": _case(row), "changed": changed, "phases": out.event_phases}

    # ------------------------------------------------------------------ user-made scenarios
    def _event(self, model: behavior.SceneModel, params: dict) -> tuple[behavior.Event, bool, float]:
        """Event, react and reaction time from the request, checked; problems as messages for the user."""
        actor = str(params.get("actor", ""))
        if actor not in model.index or not model.vehicles[model.index[actor]] or actor == "ego":
            raise SourceError(f"Không có xe '{actor}' để cho phanh trong cảnh này.")
        a = model.agents[model.index[actor]]
        try:
            t0, decel = float(params.get("t0")), float(params.get("decel"))
            dwell = float(params.get("dwell", 0.0))
            reaction = float(params.get("reaction", behavior.REACTION))
        except (TypeError, ValueError) as exc:
            raise SourceError("Tham số phải là số.") from exc
        target = params.get("target", "stop")
        if target not in ("stop", "half"):
            raise SourceError("Đích phải là 'stop' (dừng) hoặc 'half' (chậm lại còn nửa tốc độ).")
        if not 0.5 <= decel <= a.max_decel + 1e-9:
            heavy = " (xe buýt, xe tải)" if a.max_decel < behavior.MAX_DECEL else ""
            raise SourceError(f"Mức phanh phải từ 0,5 tới {a.max_decel:g} m/s² với xe này{heavy}.")
        if not 0.0 <= dwell <= 10.0 or not 0.3 <= reaction <= 3.0:
            raise SourceError("Thời gian dừng phải từ 0 tới 10 s, thời gian phản xạ từ 0,3 tới 3 s.")
        k0 = int(round(t0 / behavior.DT))
        if not 0 <= k0 < model.K or np.isnan(model.V[k0, model.index[actor]]):
            raise SourceError(f"Lúc {t0:g} s xe {actor} không có trong dữ liệu.")
        if model.V[k0, model.index[actor]] < 1.0:
            raise SourceError(f"Lúc {t0:g} s xe {actor} gần như đang đứng yên, không có gì để phanh.")
        return behavior.Event(actor, round(t0, 2), decel, target, dwell if target == "stop" else 0.0), \
            bool(params.get("react", True)), reaction

    def simulate_event(self, source_id: str, name: str, params: dict) -> dict:
        """A scenario the user made: every vehicle it changes (trajectory, state over time, the vehicle it
        followed), series for the charts, events on the timeline, and the checks with measured values."""
        model = self.model(source_id, name)
        event, react, reaction = self._event(model, params)
        out = behavior.simulate(model, event, react, reaction)
        a = events.assess(model, out)
        X, Y, H = behavior.centres(model, out)
        t = model.t
        keep = slice(None, None, SERIES_STEP)
        changed, series = {}, {}
        names = [x.name for x in model.agents]
        for i in np.flatnonzero(out.changed):
            ti, ref, heading = behavior.poses(model, out, i)
            k = slice(None, None, SERIES_STEP)
            present = ~np.isnan(out.S[:, i])
            modes = [behavior.MODE_NAMES[m] if p else None for m, p in zip(out.mode[:, i], present)]
            leaders = [names[j] if j >= 0 else None for j in out.leader[:, i]]
            changed[names[i]] = {
                "role": "event" if names[i] == event.actor else "reacted",
                "poses": {"t": _round(ti[k], 3), "x": _round(ref[k, 0], 3), "y": _round(ref[k, 1], 3),
                          "yaw": _round(heading[k], 4)},
                "modes": [m for m in _segments(t, modes) if m[2] is not None],
                "leaders": [m for m in _segments(t, leaders) if m[2] is not None],
            }
        e = model.index["ego"]
        watch = sorted(set(np.flatnonzero(out.changed)) | {e})
        for i in watch:
            v = out.V[:, i]
            series[names[i]] = {"v": _series(v[keep]), "v_rec": _series(model.V[keep, i]),
                                "a": _series(np.gradient(np.nan_to_num(v, nan=0.0), behavior.DT)[keep]
                                             * np.where(np.isnan(v[keep]), np.nan, 1.0))}
        # the ego's gap and time to collision to whatever is ahead of it, on the simulated positions
        gap, ttc = np.full(model.K, np.nan), np.full(model.K, np.nan)
        pres = ~np.isnan(X)
        for k in range(0, model.K, SERIES_STEP):
            if not pres[k, e]:
                continue
            j, g = behavior.find_leader(model, e, out.S[k, e], X[k], Y[k], H[k], out.V[k], pres[k])
            if j >= 0:
                gap[k] = g
                closing = out.V[k, e] - out.V[k, j] * math.cos(behavior._wrap(H[k, j] - H[k, e]))
                ttc[k] = g / closing if closing > 0.05 else np.nan
        series["ego"].update(gap=_series(gap[keep]), ttc=_series(np.minimum(ttc, 99.0)[keep]))
        markers = [{"t": v, "kind": key, "agent": event.actor} for key, v in out.event_phases.items()]
        markers += [{"t": round(float(v), 2), "kind": "reacts", "agent": who} for who, v in out.driving_from.items()
                    if who != event.actor]
        if np.isfinite(gap).any():
            k = int(np.nanargmin(gap))
            markers.append({"t": round(float(t[k]), 2), "kind": "closest", "agent": "ego",
                            "value": round(float(gap[k]), 2)})
        markers += [{"t": c[2], "kind": "collision", "agent": c[0], "other": c[1], "type": c[3]} for c in a.collisions]
        return {
            "event": {"actor": event.actor, "t0": event.t0, "decel": event.decel, "target": event.target,
                      "dwell": event.dwell, "react": react, "reaction": reaction, "id": events.variant_id(event)},
            "t": _round(t[keep], 2), "changed": changed, "series": series, "markers": sorted(markers, key=lambda m: m["t"]),
            "result": {"valid": a.valid, "reasons": a.reasons, "group": a.group, "ego": a.ego, "reacted": a.reacted,
                       "max_decel_used": a.max_decel_used, "collisions": a.collisions, "details": a.details},
        }

    def export_event(self, source_id: str, name: str, params: dict) -> dict:
        """Replay a user-made scenario in esmini and pack its files (pipeline.export_event) as a .zip."""
        exe = find_esmini(self.esmini)
        if exe is None:
            raise PipelineError("Không tìm thấy esmini, nên chưa kiểm lại và xuất được.")
        model = self.model(source_id, name)
        event, react, reaction = self._event(model, params)
        source = self.source(source_id)
        vid = events.variant_id(event) + ("" if react else "_noreact") \
            + ("" if reaction == behavior.REACTION else f"_r{reaction:.1f}")
        folder = scene_dir(self.out_root, source, name) / "exports" / vid
        report = export_event(source, name, event, exe, folder, react, reaction, model=model)
        shutil.make_archive(str(folder), "zip", folder)
        return {"id": vid, "report": report, "download": f"/api/download?source={source_id}&name={name}&id={vid}"}

    def rare_package(self, source_id: str, name: str) -> Path:
        """The rare-case scenarios the processing kept for a scene (events/pilot/xosc), as one .zip."""
        folder = scene_dir(self.out_root, self.source(source_id), name) / "events" / "pilot"
        if not any((folder / "xosc").glob("*.xosc")):
            raise SourceError("Cảnh này chưa có ca hiếm nào được lưu.")
        target = folder / f"{name}_ca_hiem"
        shutil.make_archive(str(target), "zip", folder / "xosc")
        return target.with_suffix(".zip")

    def download(self, source_id: str, name: str, export_id: str) -> Path:
        if export_id == "rare":
            return self.rare_package(source_id, name)
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", export_id):
            raise SourceError("Tên file không hợp lệ.")
        path = scene_dir(self.out_root, self.source(source_id), name) / "exports" / f"{export_id}.zip"
        if not path.is_file():
            raise SourceError("Chưa có file này. Bấm \"Tải\" để tạo lại.")
        return path

    # ------------------------------------------------------------------ viewer
    def scene(self, source_id: str, name: str) -> dict:
        key = (source_id, name)
        with self._lock:
            cached = self._scenes.get(key)
        if cached is None:
            cached = self._build_scene(self.source(source_id), name)
            with self._lock:
                self._scenes[key] = cached
        return cached

    def _build_scene(self, source: Source, name: str) -> dict:
        if name not in source.scene_names():
            raise SourceError(f"Không có cảnh '{name}' trong nguồn '{source.id}'.")
        gt = source.scene(name)
        folder = scene_dir(self.out_root, source, name)
        recon = {method: {t.name: t for t in reconstruct(gt, method).tracks} for method in ("baseline", "pilot")}
        metrics = {m: _read_json(folder / m / "metrics.json") for m in METHODS}

        tracks = []
        for track in gt.tracks:
            tracks.append({
                "name": track.name, "category": track.category, "kind": track.kind,
                "size": _round(track.size, 3), "bbox_center_x": track.bbox_center_x,
                "stationary": track.is_stationary, "keyframes": len(track.t),
                "gt": track_poses(track),
                "baseline": track_poses(recon["baseline"][track.name]),
                "pilot": track_poses(recon["pilot"][track.name]),
                "errors": {m: metrics[m]["per_track"].get(track.name) for m in METHODS if metrics[m]},
            })

        per_method, run = {}, None
        for method in ("baseline", "pilot"):
            report = _read_json(folder / "events" / method / "report.json")
            if report:
                cases = [_case(v) for v in report["variants"] if v["valid"]]
                grid = [{"id": v["id"], "actor": v["actor"], "t0": v["t0"], "decel": v["decel"], "target": v["target"],
                         "dwell": v["dwell"], "valid": v["valid"], "group": v["group"], "reasons": v["reasons"],
                         "min_gap": (v.get("ego") or {}).get("min_gap"), "a_used": (v.get("ego") or {}).get("a_used")}
                        for v in report["variants"]]
                per_method[method] = {"summary": report["summary"], "cases": cases, "grid": grid}
                run = run or report.get("run")
        model = self.model(source.id, name)
        drivers = {a.name: {"T": round(a.T, 2), "s0": round(a.s0, 2), "T_measured": a.T_measured,
                            "s0_measured": a.s0_measured, "max_decel": a.max_decel}
                   for a in model.agents if a.vehicle and not a.static}

        origin = np.asarray(gt.origin, float)
        layers = source.map_layers(name, scene_box(gt, VIEW_MARGIN))
        ring = lambda points: _round(points - origin, 2)  # noqa: E731
        map_payload = {}
        for layer, items in layers.items():
            if items and isinstance(items[0], tuple):  # polygons: (exterior, holes)
                map_payload[layer] = [{"ext": ring(ext), "holes": [ring(h) for h in holes]} for ext, holes in items]
            else:  # polylines
                map_payload[layer] = [ring(line) for line in items]

        return {
            "source": source.id, "name": name,
            "description": source.description(name),
            "location": source.location(name),
            "origin": list(gt.origin),
            "duration": gt.duration,
            "map": map_payload,
            "tracks": tracks,
            "summary": {m: metrics[m]["summary"] for m in METHODS if metrics[m]},
            "variants": per_method,
            "selectable": events.selectable(model),
            "label_problems": events.label_problems(model),
            "drivers": drivers,
            "thresholds": events.thresholds(),
            "code": code_version(),
            "run": {"code": (run or {}).get("code"), "esmini": ((run or {}).get("esmini") or {}).get("version"),
                    "created": (run or {}).get("created")},
        }

    # ------------------------------------------------------------------ processing
    def process(self, source_id: str, scenes: list[str] | None = None) -> list[dict]:
        """Queue scenes for processing; scenes=None means every scene not processed yet."""
        if find_esmini(self.esmini) is None:
            raise PipelineError("Không tìm thấy esmini. Giải nén esmini vào thư mục tools\\esmini-demo\\ "
                                "của dự án (xem README), rồi thử lại.")
        source = self.source(source_id)
        if scenes is None:
            scenes = [row["name"] for row in self.scene_list(source_id) if not row["processed"]]
        unknown = [s for s in scenes if s not in source.scene_names()]
        if unknown:
            raise SourceError(f"Không có cảnh: {', '.join(unknown)}")
        return [self.runner.submit(source_id, name).public() for name in scenes]

    def jobs(self) -> list[dict]:
        return self.runner.list()

    def _run_job(self, job: Job, log, progress) -> None:
        exe = find_esmini(self.esmini)
        if exe is None:
            raise PipelineError("Không tìm thấy esmini.")
        process_scene(self.source(job.source), job.scene, self.out_root, exe, log=log, progress=progress)

    def _job_done(self, job: Job) -> None:
        with self._lock:  # numbers changed: rebuild this scene's payload on next request
            self._scenes.pop((job.source, job.scene), None)
            self._models.pop((job.source, job.scene), None)
