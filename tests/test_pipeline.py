"""variants_scene orchestration with a fake esmini that replays every track exactly."""

import json
from pathlib import Path

import numpy as np
import pytest

from real2sim import pipeline
from real2sim.esmini import SimTrack
from real2sim.pipeline import PipelineError, Replay, variants_scene
from real2sim.sources import Source
from real2sim.tracks import Scene, Track
from real2sim.xosc import write_xosc

T = np.arange(0, 10.01, 0.5)


def track(name, xy, category="vehicle.car", t=T):
    return Track(name, category, t, np.asarray(xy, float), np.zeros(len(t)), (4.0, 2.0, 1.5),
                 bbox_center_x=1.39 if name == "ego" else 0.0)


def make_scene():
    rng = np.random.default_rng(7)
    ego = track("ego", np.column_stack([5 * T, rng.normal(0, 0.1, len(T))]), "vehicle.ego")
    lead = track("car_001", np.column_stack([15 + 5 * T, rng.normal(0, 0.1, len(T))]))  # 15 m ahead, same speed
    parked = track("car_002", [[60, 10], [60, 10]], t=T[[0, -1]])
    return Scene("s", (0.0, 0.0), 10.0, [ego, lead, parked])


class FakeSource(Source):
    def __init__(self, scene):
        super().__init__("fake", "Fake")
        self._scene = scene

    def scene_names(self):
        return [self._scene.name]

    def scene(self, name):
        return self._scene


def exact_log(scene, dt=0.05):
    out = {}
    for tr in scene.tracks:
        t = np.arange(tr.t[0], tr.t[-1] + 1e-9, dt)
        xy = np.column_stack([np.interp(t, tr.t, tr.xy[:, k]) for k in (0, 1)])
        out[tr.name] = SimTrack(t, xy, np.interp(t, tr.t, tr.yaw), np.zeros_like(t))
    return out


@pytest.fixture
def fake_esmini(monkeypatch):
    """Replaces simulate(); records the scenes it is given. fail(workdir, xosc) -> True makes a run fail."""
    calls, rules = [], {"fail": lambda workdir, xosc: False}

    def simulate(exe, scene, workdir, dt, xosc=None, xodr=None):
        workdir.mkdir(parents=True, exist_ok=True)
        path = write_xosc(scene, xosc or workdir / "scenario.xosc", xodr)
        calls.append((workdir, scene))
        if rules["fail"](workdir, xosc):
            path.unlink() if xosc else None
            return Replay(1, None, ["fake failure"])
        return Replay(0, exact_log(scene), [], "v-test")

    monkeypatch.setattr(pipeline, "simulate", simulate)
    monkeypatch.setattr("real2sim.variants.grid", lambda track=None: [(0.6, 0.0, 0.0), (1.4, 0.0, 0.0), (1.0, 5.0, 0.0)])
    return calls, rules


def run(tmp_path, gt, keep="rare"):
    return variants_scene(FakeSource(gt), "s", tmp_path, Path("esmini"), road="none", jobs=1, keep=keep)


def test_variants_scene(tmp_path, fake_esmini):
    calls, _ = fake_esmini
    gt = make_scene()
    summaries = run(tmp_path, gt)
    out = tmp_path / "fake" / "s"
    assert (out / "tracks_gt.json").is_file()  # audit 2.5: report finds scenes run by variants only
    assert not list(out.rglob("*.new"))

    # audit 1.1: every replayed scene holds the recorded ego, for baseline and pilot alike
    for _, scene in calls:
        ego = next(tr for tr in scene.tracks if tr.name == "ego")
        assert ego.t.tolist() == gt.tracks[0].t.tolist() and ego.xy.tolist() == gt.tracks[0].xy.tolist()

    reports = {m: json.loads((out / "variants" / m / "report.json").read_text(encoding="utf-8"))
               for m in ("baseline", "pilot")}
    # audit 1.3a: the reference is the recording, the same for both methods
    assert reports["baseline"]["recorded"] == reports["pilot"]["recorded"]
    run_block = reports["pilot"]["run"]  # audit 2.6
    assert run_block["esmini"]["version"] == "v-test" and run_block["config"]["methods"] == ["baseline", "pilot"]
    assert "commit" in run_block["code"]

    # the lead car at 60 % speed: the ego runs into it, but braking at about 0.5 m/s^2 after detection
    # (TTC < 3 s) and 1 s reaction avoids it, so version 1 calls it rare and version 2 does not
    slow = next(row for row in reports["pilot"]["variants"] if row["factor"] == 0.6)
    assert slow["rare"] and slow["crash"] and slow["conflict"] == "front" and slow["actor"] == "vehicle"
    assert slow["group"] == "mild" and not slow["valuable"]
    assert slow["braking"]["r1.0_d3.0"]["a_need"] <= 1.0
    assert not slow.get("kept")  # only valuable variants are written as deliverables
    assert summaries["pilot"]["rare_events"] <= summaries["pilot"]["rare"]
    assert summaries["pilot"]["groups"]["mild"] >= 1


def test_failed_run_keeps_previous_results(tmp_path, fake_esmini):
    """Audit 2.4: results are replaced only when the new run succeeds; the failed run's files stay."""
    _, rules = fake_esmini
    gt = make_scene()
    run(tmp_path, gt)
    out = tmp_path / "fake" / "s" / "variants"
    before = {m: (out / m / "report.json").read_bytes() for m in ("baseline", "pilot")}
    rules["fail"] = lambda workdir, xosc: workdir.name == "original" and workdir.parent.parent.name == "pilot.new"
    with pytest.raises(PipelineError):
        run(tmp_path, gt)
    assert {m: (out / m / "report.json").read_bytes() for m in ("baseline", "pilot")} == before
    assert (out / "pilot.new").is_dir()


def test_failed_full_replay_is_not_valid(tmp_path, fake_esmini):
    """Audit 2.2: a kept variant whose full replay fails is invalid, with its reason, and not kept."""
    _, rules = fake_esmini
    rules["fail"] = lambda workdir, xosc: xosc is not None
    summaries = run(tmp_path, make_scene(), keep="valid")
    report = json.loads((tmp_path / "fake" / "s" / "variants" / "pilot" / "report.json").read_text(encoding="utf-8"))
    failed = [row for row in report["variants"] if "full_replay" in row["reasons"]]
    assert failed and all(not row["valid"] and not row["rare"] and not row["kept"] for row in failed)
    assert summaries["pilot"]["valid"] == 0 and summaries["pilot"]["kept_xosc"] == 0
    assert summaries["pilot"]["full_replay_failed"] == len(failed)
    assert not list((tmp_path / "fake" / "s" / "variants" / "pilot" / "xosc").glob("*.xosc"))


def test_export_event_writes_a_checked_package(tmp_path, fake_esmini):
    """A user-made scenario: files a test engineer can use, the replay error measured on the esmini log."""
    from real2sim import behavior

    gt = make_scene()
    report = pipeline.export_event(FakeSource(gt), "s", behavior.Event("car_001", 2.0, 4.0, "stop", 1.0),
                                   Path("esmini"), tmp_path / "pack", road="none")
    files = sorted(p.name for p in (tmp_path / "pack").iterdir())
    assert files == ["car_001_t02.0_stop_d1_a4.xosc", "report.json", "trajectories.csv"]
    assert report["valid"] and report["event"]["actor"] == "car_001" and report["drivers"]["reaction_s"] == 1.0
    assert report["esmini"]["replay_error_m"]["car_001"]["max"] < 0.05  # the fake replays what it is given
    assert set(report["checks"]) == {"physics", "excused", "gaps"}
    assert json.loads((tmp_path / "pack" / "report.json").read_text(encoding="utf-8"))["id"] == report["id"]


def test_events_scene_runs_in_process_with_a_chosen_reaction_time(tmp_path, fake_esmini):
    from real2sim.pipeline import events_scene

    gt = make_scene()
    summaries = events_scene(FakeSource(gt), "s", tmp_path, Path("esmini"), road="none", jobs=1, reaction=1.5)
    report = json.loads((tmp_path / "fake" / "s" / "events" / "pilot" / "report.json").read_text(encoding="utf-8"))
    assert report["run"]["config"]["reaction_s"] == 1.5
    assert summaries["pilot"]["attempted"] == summaries["baseline"]["attempted"] > 0
