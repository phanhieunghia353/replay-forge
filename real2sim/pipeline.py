"""Processing steps shared by the command line and the web app.

  replay_scene     metric 1: write exact/baseline/pilot scenarios, replay in esmini, replay error
  variants_scene   metric 2: speed/offset variants, validity, rarity
  process_scene    both, one after the other

Results go to <out_root>/<source.id>/<scene>/ (see docs/kien-truc.md). Every function takes
`log(text)` for human-readable lines and `progress(fraction, text)` for a progress bar.

A run writes into "<folder>.new" next to each result folder and swaps it in only when the whole step
has succeeded, so a failed run leaves the previous results (and its own logs, in the .new folder).
Every metrics.json / report.json holds a "run" block: code commit, esmini version, configuration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from real2sim import variants
from real2sim.abstraction import METHODS, reconstruct
from real2sim.esmini import EsminiError, log_problems, read_csv_log, read_preamble, run_esmini
from real2sim.metrics import evaluate, format_comparison, format_summary
from real2sim.sources import Source
from real2sim.tracks import Scene
from real2sim.xodr import write_flat_pad, write_map_roads
from real2sim.xosc import write_xosc

Log = Callable[[str], None]
Progress = Callable[[float, str], None]
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PipelineError(RuntimeError):
    """Processing could not finish (esmini failed, …); message written for the user."""


def _quiet(*_):
    pass


def scene_dir(out_root: str | Path, source: Source, scene_name: str) -> Path:
    return Path(out_root) / source.id / scene_name


# ---------------------------------------------------------------------------- run bookkeeping
def code_version() -> dict:
    """Git commit of this code and whether the package has uncommitted changes (None without git)."""
    def git(*args):
        try:
            run = subprocess.run(["git", "-C", str(PROJECT_ROOT), *args], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ""
        return run.stdout.strip() if run.returncode == 0 else ""

    commit = git("rev-parse", "HEAD") or None
    dirty = bool(git("status", "--porcelain", "--untracked-files=no", "--", "real2sim")) if commit else None
    return {"commit": commit, "dirty": dirty}


def run_info(source: Source, scene_name: str, exe: Path | None, esmini_version: str | None, config: dict) -> dict:
    return {"created": datetime.now().replace(microsecond=0).isoformat(), "code": code_version(),
            "esmini": {"path": str(exe) if exe else None, "version": esmini_version},
            "source": source.id, "scene": scene_name, "config": config}


def _fresh(folder: Path) -> Path:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    return folder


def _swap(staged: dict[Path, Path]) -> None:
    """Replace each final folder by its staged one."""
    for new, final in staged.items():
        old = final.with_name(final.name + ".old")
        if old.exists():
            shutil.rmtree(old)
        if final.exists():
            final.rename(old)
        new.rename(final)
        if old.exists():
            shutil.rmtree(old)


def _save_tracks(gt: Scene, out: Path) -> None:
    tmp = out / "tracks_gt.json.new"
    gt.save(tmp)
    tmp.replace(out / "tracks_gt.json")


def write_road(source: Source, gt: Scene, folder: Path, road: str, log: Log = _quiet) -> str | None:
    """Write the scene's OpenDRIVE file into folder; returns its file name, or None for no road.
    road = "map": the source's own .xodr if it has one, else lanes from its map, else none."""
    if road == "none":
        return None
    if road == "flat":
        return write_flat_pad(gt, folder / f"{gt.name}_flat.xodr").name
    ready = source.road_file(gt.name)
    if ready is not None:
        target = folder / f"{gt.name}.xodr"
        shutil.copyfile(ready, target)
        return target.name
    lanes = source.road_lanes(gt.name, gt)
    if not lanes:
        log(f"{gt.name}: no map for this scene; scenarios have no road network")
        return None
    return write_map_roads(gt, lanes, folder / f"{gt.name}_map.xodr").name


@dataclass
class Replay:
    code: int
    sim: dict | None  # None when esmini failed or its log does not cover every track
    problems: list[str] = field(default_factory=list)
    version: str | None = None

    @property
    def failure(self) -> str:
        return f"esmini_exit_{self.code}" if self.code != 0 else "log_incomplete"


def simulate(exe: Path, scene: Scene, workdir: Path, dt: float, xosc: Path | None = None,
             xodr: str | None = None) -> Replay:
    """Write and replay one scenario (esmini output in workdir); the log must cover every track of the
    scene over its time span. xodr is a file name next to the xosc."""
    workdir.mkdir(parents=True, exist_ok=True)
    xosc = write_xosc(scene, xosc or workdir / "scenario.xosc", xodr, date="2026-01-01T00:00:00")
    run = run_esmini(exe, xosc, workdir / "log.csv", dt=dt)
    result = Replay(run.returncode, None)
    if run.returncode == 0 and run.csv_path.is_file():
        try:
            sim = read_csv_log(run.csv_path)
            result.problems = log_problems(scene.tracks, sim)
            result.version = read_preamble(run.csv_path).get("esmini GIT TAG")
        except EsminiError as exc:
            result.problems = [str(exc)]
        else:
            result.sim = None if result.problems else sim
    elif run.returncode == 0:
        result.problems = ["no log written"]
    if result.sim is None:
        (workdir / "esmini_stdout.txt").write_text("\n".join(result.problems) + "\n" + run.stdout + run.stderr,
                                                   encoding="utf-8")
    for name in ("log.csv", "log.txt"):
        (workdir / name).unlink(missing_ok=True)
    return result


# ---------------------------------------------------------------------------- metric 1
def replay_scene(source: Source, scene_name: str, out_root: str | Path, exe: Path | None,
                 methods=METHODS, road: str = "map", dt: float = 0.05,
                 log: Log = _quiet, progress: Progress = _quiet) -> dict:
    """Write scenarios for each method and replay them; returns {method: summary}.
    With exe=None the scenarios are written and replay is skipped (returns {})."""
    out = scene_dir(out_root, source, scene_name)
    out.mkdir(parents=True, exist_ok=True)
    gt = source.scene(scene_name)
    moving = sum(not track.is_stationary for track in gt.tracks)
    log(f"{scene_name}: {len(gt.tracks)} tracks ({moving} moving), {gt.duration:.1f} s")

    scenarios, staged = {}, {}
    for method in methods:
        folder = _fresh(out / f"{method}.new")
        staged[folder] = out / method
        scenarios[method] = write_xosc(reconstruct(gt, method), folder / f"{scene_name}.xosc",
                                       write_road(source, gt, folder, road, log))
        log(f"  {method:<9} -> {out / method / scenarios[method].name}")
    if exe is None:
        _save_tracks(gt, out)
        _swap(staged)
        return {}

    summaries, results = {}, {}
    for k, (method, xosc) in enumerate(scenarios.items()):
        progress(k / len(scenarios), f"esmini: {method}")
        run = run_esmini(exe, xosc, xosc.parent / "esmini_log.csv", dt=dt)
        stdout = xosc.parent / "esmini_stdout.txt"
        stdout.write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode != 0 or not run.csv_path.is_file():
            raise PipelineError(f"esmini lỗi khi phát lại {scene_name} ({method}), mã thoát {run.returncode}. "
                                f"Kết quả cũ được giữ nguyên. Xem {stdout}")
        sim = read_csv_log(run.csv_path)
        problems = log_problems(gt.tracks, sim)
        if problems:
            raise PipelineError(f"Log esmini của {scene_name} ({method}) thiếu dữ liệu: {'; '.join(problems[:5])}"
                                f"{' …' if len(problems) > 5 else ''}. Kết quả cũ được giữ nguyên.")
        result = evaluate(gt.tracks, sim)
        result["run"] = run_info(source, scene_name, exe, read_preamble(run.csv_path).get("esmini GIT TAG"),
                                 {"method": method, "road": road, "dt": dt})
        results[method] = result
        summaries[method] = result["summary"]
        log(f"\n[{method}] esmini exit code 0\n{format_summary(result['summary'])}")
    for method, result in results.items():
        (out / f"{method}.new" / "metrics.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    _save_tracks(gt, out)
    _swap(staged)
    if len(summaries) > 1:
        log("\nreplay error vs raw keyframe labels\n" + format_comparison(summaries))
    progress(1.0, "xong")
    return summaries


# ---------------------------------------------------------------------------- metric 2
def variants_scene(source: Source, scene_name: str, out_root: str | Path, exe: Path,
                   methods=("baseline", "pilot"), road: str = "map", dt: float = 0.05, jobs: int = 4,
                   max_targets: int = 0, keep: str = "rare",
                   log: Log = _quiet, progress: Progress = _quiet) -> dict:
    """Speed/offset variants of every moving vehicle, replayed in esmini; returns {method: summary}."""
    gt = source.scene(scene_name)
    out = scene_dir(out_root, source, scene_name)
    root = out / "variants"
    root.mkdir(parents=True, exist_ok=True)
    names = variants.targets(gt)[: max_targets or None]
    by_name = {track.name: track for track in gt.tracks}
    tasks = [(t, f, d, s) for t in names for f, d, s in variants.grid(by_name[t])]
    log(f"{scene_name}: {len(names)} actors, {len(tasks)} variants per method")
    drivable = source.drivable(scene_name)
    config = {"methods": list(methods), "road": road, "dt": dt, "max_targets": max_targets, "keep": keep,
              "grid": {"speed_factors": variants.SPEED_FACTORS, "offsets_m": variants.OFFSETS,
                       "pedestrian_offsets_m": variants.PEDESTRIAN_OFFSETS, "time_shifts_s": variants.TIME_SHIFTS},
              "thresholds": variants.thresholds()}

    def label(row: dict, target: str) -> dict:
        return {**row, "target": target, "actor": variants.actor_class(by_name[target])}

    pedestrians = frozenset(track.name for track in gt.tracks if track.kind == "pedestrian")

    def check_actor(box, around, target):
        """variants.assess with the actor's limits; a pedestrian may touch other pedestrians."""
        soft = pedestrians if by_name[target].kind == "pedestrian" else frozenset()
        return variants.assess(box, around, allowed[target], variants.limits(by_name[target]), soft, gt.duration)

    # The recording, replayed once: the reference for excused overlaps and for "rare in the recording",
    # the same for every method.
    rec = simulate(exe, gt, root / "_recorded", dt)
    if rec.sim is None:
        raise PipelineError(f"esmini lỗi khi phát lại {scene_name} theo bản ghi ({rec.failure}: "
                            f"{'; '.join(rec.problems[:3])}). Kết quả cũ được giữ nguyên.")
    shutil.rmtree(root / "_recorded", ignore_errors=True)
    allowed, recorded = {}, {}
    for target in names:
        around = variants.other_boxes(gt, gt, rec.sim, target)
        box = variants.target_box(gt, rec.sim, target)
        allowed[target] = variants.overlap_times(box, around)
        recorded[target] = label(check_actor(box, around, target), target)

    total = max(1, len(methods) * len(tasks))
    finished = 0
    counter_lock = threading.Lock()
    summaries, staged = {}, {}
    for method in methods:
        folder = _fresh(root / f"{method}.new")
        (folder / "xosc").mkdir()
        xodr = write_road(source, gt, folder / "xosc", road, log)
        base = variants.method_scene(gt, method)
        start = simulate(exe, base, folder / "_work" / "original", dt)
        if start.sim is None:
            raise PipelineError(f"esmini lỗi khi phát lại {scene_name} gốc ({method}, {start.failure}: "
                                f"{'; '.join(start.problems[:3])}). Kết quả cũ được giữ nguyên.")

        # Objects other than the target are unchanged in every variant, so their replayed boxes come
        # from this full replay; each variant is checked by replaying only the target and the ego.
        original, others = {}, {}
        for target in names:
            others[target] = variants.other_boxes(gt, base, start.sim, target)
            box = variants.target_box(base, start.sim, target)
            original[target] = label(check_actor(box, others[target], target), target)
            if drivable is not None and box is not None and by_name[target].kind == "vehicle":
                original[target]["on_road_fraction"] = variants.on_road_fraction(box, drivable, gt.origin)

        def job(target, factor, offset, shift):
            vid = variants.variant_id(target, factor, offset, shift)
            row = label({"id": vid, "factor": factor, "offset": offset, "shift": shift}, target)
            scene = variants.variant_scene(base, target, factor, offset, shift)
            if scene is None:
                return {**row, "valid": False, "reasons": ["span"], "rare": False, "group": None, "valuable": False}
            work = folder / "_work" / vid
            reduced = Scene(scene.name, scene.origin, scene.duration,
                            [tr for tr in scene.tracks if tr.name in ("ego", target)])
            replay = simulate(exe, reduced, work, dt)
            if replay.sim is None:
                return {**row, "valid": False, "reasons": [replay.failure], "problems": replay.problems, "rare": False,
                        "group": None, "valuable": False}
            row.update(check_actor(variants.target_box(scene, replay.sim, target), others[target], target))
            if keep == "valid" and row["valid"] or keep == "rare" and row["valuable"]:
                # the delivered file holds the whole scene and the road: replay it in full too
                delivered = folder / "xosc" / f"{vid}.xosc"
                full = simulate(exe, scene, work, dt, xosc=delivered, xodr=xodr)
                row["full_replay_exit"] = full.code
                if full.sim is None:
                    delivered.unlink(missing_ok=True)
                    row.update(valid=False, rare=False, group=None, valuable=False,
                               reasons=row["reasons"] + ["full_replay"], problems=full.problems)
                row["kept"] = delivered.is_file()
            shutil.rmtree(work, ignore_errors=True)
            return row

        def counted(task):
            nonlocal finished
            row = job(*task)
            with counter_lock:
                finished += 1
                done = finished
            if done % 10 == 0 or done == total:
                progress(done / total, f"biến thể {method}: {done}/{total}")
            return row

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            rows = list(pool.map(counted, tasks))
        shutil.rmtree(folder / "_work", ignore_errors=True)

        summary = variants.summarize(rows, original, recorded)
        summaries[method] = summary
        payload = {"scene": scene_name, "source": source.id, "method": method, "road": road, "xodr": xodr,
                   "grid": config["grid"], "thresholds": config["thresholds"],
                   "run": run_info(source, scene_name, exe, start.version or rec.version, config),
                   "summary": summary, "recorded": recorded, "original": original, "variants": rows}
        (folder / "report.json").write_text(json.dumps(payload, indent=1, default=float), encoding="utf-8")
        staged[folder] = root / method
        log(f"\n[{method}] {root / method / 'report.json'}\n{variants.format_summary(summary)}")
    _save_tracks(gt, out)
    _swap(staged)
    if len(summaries) > 1:
        log("\n" + variants.format_comparison(summaries))
    progress(1.0, "xong")
    return summaries


# ---------------------------------------------------------------------------- stage 1 events (metric 2, redesign)
_WORKER: dict = {}


def _events_worker_init(gt: Scene) -> None:
    from real2sim import behavior

    _WORKER["gt"], _WORKER["model"] = gt, behavior.SceneModel(gt)


def _events_job(job) -> dict:
    """Simulate, assess and (when valid) replay one variant in esmini; runs in a worker process."""
    from real2sim import behavior, events

    event, react, exe, folder, xodr, dt, keep, reaction = job
    gt, model = _WORKER["gt"], _WORKER["model"]
    out = behavior.simulate(model, event, react, reaction)
    a = events.assess(model, out)
    vid = events.variant_id(event)
    row = {"id": vid, "encounter": events.encounter_id(event), "actor": event.actor, "t0": event.t0,
           "decel": event.decel, "target": event.target, "dwell": event.dwell,
           "valid": a.valid, "reasons": list(a.reasons), "collisions": a.collisions[:5], "group": a.group,
           "ego": a.ego, "reacted": a.reacted, "entered": sorted(out.entered),
           "max_decel_used": a.max_decel_used}
    if not a.valid:
        return row
    scene = events.outcome_scene(model, gt, out)
    work = Path(folder) / "_work" / vid
    kept = keep == "valid" or keep == "rare" and a.group in events.VALUABLE
    xosc = Path(folder) / "xosc" / f"{vid}.xosc" if kept else None
    replay = simulate(exe, scene, work, dt, xosc=xosc, xodr=xodr if kept else None)
    row["esmini_exit"] = replay.code
    if replay.sim is None:
        row.update(valid=False, group=None, reasons=row["reasons"] + ["esmini"], esmini_problems=replay.problems[:3])
        if xosc is not None:
            xosc.unlink(missing_ok=True)
    else:
        row["kept"] = bool(xosc is not None and xosc.is_file())
        row["esmini_version"] = replay.version
        row["dynamics"] = events.replay_dynamics(model, out, replay.sim)
    shutil.rmtree(work, ignore_errors=True)
    return row


class _InlinePool:
    """Stand-in for ProcessPoolExecutor that runs jobs here, one after another (jobs=1, tests)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @staticmethod
    def map(fn, items, chunksize=1):
        return map(fn, items)


def events_scene(source: Source, scene_name: str, out_root: str | Path, exe: Path,
                 methods=("baseline", "pilot"), road: str = "map", dt: float = 0.05, jobs: int = 4,
                 keep: str = "rare", log: Log = _quiet, progress: Progress = _quiet,
                 reaction: float | None = None) -> dict:
    """Stage 1 (docs/thiet-ke-kich-ban-hanh-vi.md): lead-vehicle braking events; baseline = nobody reacts,
    pilot = the vehicles behind react like human drivers. Returns {method: summary}.
    reaction: the drivers' reaction time (behavior.REACTION; other values for sensitivity runs).
    jobs <= 1 runs in this process (no worker processes)."""
    from concurrent.futures import ProcessPoolExecutor

    from real2sim import behavior, events

    gt = source.scene(scene_name)
    out = scene_dir(out_root, source, scene_name)
    root = out / "events"
    root.mkdir(parents=True, exist_ok=True)
    model = behavior.SceneModel(gt)
    cands = events.candidates(model)
    log(f"{scene_name}: {len(cands)} variants in {len({events.encounter_id(e) for e in cands})} encounters per method")
    reaction = behavior.REACTION if reaction is None else reaction
    config = {"methods": list(methods), "road": road, "dt": dt, "keep": keep, "reaction_s": reaction,
              "grid": events.grid_config(), "thresholds": events.thresholds()}
    summaries, staged = {}, {}
    total = max(1, len(methods) * len(cands))
    done = 0
    if jobs <= 1:
        _events_worker_init(gt)
        pool = _InlinePool()
    else:
        pool = ProcessPoolExecutor(max_workers=jobs, initializer=_events_worker_init, initargs=(gt,))
    with pool:
        for method in methods:
            folder = _fresh(root / f"{method}.new")
            (folder / "xosc").mkdir()
            xodr = write_road(source, gt, folder / "xosc", road, log)
            react = method == "pilot"
            rows = []
            for row in pool.map(_events_job, [(e, react, exe, str(folder), xodr, dt, keep, reaction) for e in cands],
                                chunksize=4):
                rows.append(row)
                done += 1
                if done % 10 == 0 or done == total:
                    progress(done / total, f"sự kiện {method}: {done}/{total}")
            shutil.rmtree(folder / "_work", ignore_errors=True)
            summary = events.summarize(rows)
            summaries[method] = summary
            version = next((r["esmini_version"] for r in rows if r.get("esmini_version")), None)
            payload = {"scene": scene_name, "source": source.id, "method": method, "xodr": xodr,
                       "run": run_info(source, scene_name, exe, version, config), "summary": summary, "variants": rows,
                       "agents": {a.name: {"T": a.T, "s0": a.s0} for a in model.agents if a.vehicle and not a.static}}
            (folder / "report.json").write_text(json.dumps(payload, indent=1, default=float), encoding="utf-8")
            staged[folder] = root / method
            log(f"\n[{method}] {root / method / 'report.json'}\n{events.format_summary(summary)}")
    _save_tracks(gt, out)
    _swap(staged)
    progress(1.0, "xong")
    return summaries


def export_event(source: Source, scene_name: str, event, exe: Path, folder: str | Path, react: bool = True,
                 reaction: float | None = None, road: str = "map", dt: float = 0.05, model=None) -> dict:
    """One user-made stage-1 scenario as files a test engineer can use, replayed in esmini first:
    <id>.xosc, the road (.xodr), trajectories.csv (every object, the real2sim CSV format) and report.json
    (parameters, checks, esmini replay error, versions). folder is emptied first. model: a prebuilt
    behavior.SceneModel of the scene (it is rebuilt otherwise)."""
    from real2sim import behavior, events
    from real2sim.sources import write_tracks_csv

    gt = source.scene(scene_name)
    model = model or behavior.SceneModel(gt)
    reaction = behavior.REACTION if reaction is None else reaction
    out = behavior.simulate(model, event, react, reaction)
    a = events.assess(model, out)
    vid = events.variant_id(event) + ("" if reaction == behavior.REACTION else f"_r{reaction:.1f}")
    folder = _fresh(Path(folder))
    xodr = write_road(source, gt, folder, road)
    scene = events.outcome_scene(model, gt, out)
    replay = simulate(exe, scene, folder / "_work", dt, xosc=folder / f"{vid}.xosc", xodr=xodr)
    errors = {}
    if replay.sim is not None:
        for i in np.flatnonzero(out.changed):
            name = model.agents[i].name
            t, ref, _ = behavior.poses(model, out, i)
            st = replay.sim.get(name)
            inner = (st.t >= t[0] + events.EDGE_SKIP) & (st.t <= t[-1] - events.EDGE_SKIP)
            want = np.column_stack([np.interp(st.t[inner], t, ref[:, k]) for k in (0, 1)])
            d = np.hypot(*(st.xy[inner] - want).T)
            errors[name] = {"mean": round(float(d.mean()), 4), "max": round(float(d.max()), 4)} if len(d) else None
    shutil.rmtree(folder / "_work", ignore_errors=True)
    write_tracks_csv([scene], folder / "trajectories.csv")
    report = {
        "id": vid, "scene": scene_name, "source": source.id,
        "event": {"actor": event.actor, "t0": event.t0, "decel": event.decel, "target": event.target,
                  "dwell": event.dwell},
        "drivers": {"react": react, "reaction_s": reaction, "thresholds": events.thresholds(),
                    "per_vehicle": {x.name: {"T": x.T, "s0": x.s0, "max_decel": x.max_decel}
                                    for x in model.agents if x.vehicle and not x.static}},
        "valid": a.valid and replay.sim is not None, "reasons": a.reasons + ([] if replay.sim else ["esmini"]),
        "group": a.group, "ego": a.ego, "reacted": a.reacted, "max_decel_used": a.max_decel_used,
        "checks": a.details, "collisions": a.collisions,
        "esmini": {"exit": replay.code, "problems": replay.problems[:5], "version": replay.version,
                   "replay_error_m": errors,
                   "dynamics": events.replay_dynamics(model, out, replay.sim) if replay.sim else None},
        "run": run_info(source, scene_name, exe, replay.version, {"road": road, "dt": dt}),
    }
    (folder / "report.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    return report


# ---------------------------------------------------------------------------- both
def process_scene(source: Source, scene_name: str, out_root: str | Path, exe: Path,
                  log: Log = _quiet, progress: Progress = _quiet, **event_options) -> dict:
    """Metric 1 then metric 2 (stage 1 events; the older variants_scene is only kept for the command line,
    as the historical baseline) for one scene. The replay step is short; it gets 10% of the bar."""
    replay = replay_scene(source, scene_name, out_root, exe, log=log,
                          progress=lambda f, text: progress(0.1 * f, f"chỉ số 1 – {text}"))
    ev = events_scene(source, scene_name, out_root, exe, log=log,
                      progress=lambda f, text: progress(0.1 + 0.9 * f, f"chỉ số 2 – {text}"), **event_options)
    return {"replay": replay, "events": ev}
