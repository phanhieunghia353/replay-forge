import numpy as np
import pytest

from real2sim.__main__ import main
from real2sim.esmini import SimTrack, log_problems, read_csv_log, read_preamble
from real2sim.metrics import evaluate, format_summary
from real2sim.nuscenes_io import NuScenesTables
from real2sim.tracks import extract_scene

BLOCK = (
    "#{k} Entity_Name [-], #{k} Entity_ID [-],#{k} Current_Speed [m/s], #{k} Wheel_Angle [deg], #{k} Wheel_Rotation [-],"
    "#{k} bb_x [m], #{k} bb_y [m], #{k} bb_z [m], #{k} bb_length [m], #{k} bb_width [m], #{k} bb_height [m], "
    "#{k} World_Position_X [m], #{k} World_Position_Y [m], #{k} World_Position_Z [m], "
    "#{k} Vel_X [m/s], #{k} Vel_Y [m/s], #{k} Vel_Z [m/s], #{k} Acc_X [m/s2], #{k} Acc_Y [m/s2], #{k} Acc_Z [m/s2], "
    "#{k} Distance_Travelled_Along_Road_Segment [m], #{k} Lateral_Distance_Lanem [m], #{k} lane_id, #{k} lane_offset [m], "
    "#{k} World_Heading_Angle [rad], #{k} Heading_Angle_Rate [rad/s], #{k} Relative_Heading_Angle [rad], "
    "#{k} Relative_Heading_Angle_Drive_Direction [rad], #{k} World_Pitch_Angle [rad], #{k} Road_Curvature [1/m], "
    "#{k} collision_ids, "
)


def _row(name, ident, speed, x, y, h, collisions=""):
    values = [name, ident, speed, 0, 0, 1.4, 0, 0.8, 4, 1.8, 1.5, x, y, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0, h, 0, 0, 0, 0, 0]
    return ", ".join(str(v) for v in values) + f", {collisions}, "


def write_log(path, entities, times):
    """Same layout as esmini CSV_Logger (CommonMini.cpp). entities: name -> f(t) -> (speed, x, y, h)."""
    lines = [
        "esmini GIT REV: x", "esmini GIT TAG: x", "esmini GIT BRANCH: x", "esmini BUILD VERSION: x",
        "Scenario File Name: s.xosc", f"Number of Vehicles: {len(entities)}",
    ]
    header = "Index [-], TimeStamp [s], " + "".join(BLOCK.format(k=k) for k in range(1, len(entities) + 1))
    lines.append(header.replace("#1 lane_offset [m]", "#1 lane_offset[m]"))
    for i, t in enumerate(times):
        lines.append(f"{i}, {t:f}, " + "".join(_row(n, j, *f(t), collisions="1 2 " if j else "") for j, (n, f) in enumerate(entities.items())))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_read_csv_log(tmp_path):
    write_log(tmp_path / "log.csv", {"ego": lambda t: (5, 5 * t, 0, 0), "car_001": lambda t: (10, 20, -10 + 10 * t, 1.5708)},
              np.arange(0, 1.01, 0.05))
    sim = read_csv_log(tmp_path / "log.csv")
    assert set(sim) == {"ego", "car_001"}
    assert len(sim["ego"].t) == 21
    assert sim["car_001"].xy[-1] == pytest.approx([20, 0])
    assert sim["car_001"].yaw[0] == pytest.approx(1.5708)


def test_read_csv_log_with_added_and_removed_entities(tmp_path):
    """Rows hold one block per entity present; the header counts only those present at the start
    (esmini 3.9.0 with AddEntityAction / DeleteEntityAction)."""
    path = tmp_path / "log.csv"
    write_log(path, {"ego": lambda t: (5, 5 * t, 0, 0)}, np.arange(0, 1.01, 0.5))
    lines = path.read_text(encoding="utf-8").splitlines()
    car = lambda t: _row("car_001", 1, 8, 10 + 8 * t, 4, 0)  # noqa: E731
    lines[-2] = lines[-2] + car(0.5)  # car added at 0.5 s: a block appended to the row
    lines[-1] = lines[-1] + ", , , "  # removed again at 1.0 s: empty trailing fields
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sim = read_csv_log(path)
    assert len(sim["ego"].t) == 3
    assert list(sim["car_001"].t) == [0.5] and sim["car_001"].xy[0] == pytest.approx([14, 4])


def test_log_problems(dataroot):
    """Audit 2.1: a log that misses a track, misses part of its time span, or holds NaN is not scored."""
    scene = extract_scene(NuScenesTables(dataroot), "scene-0001")
    sim = {t.name: _perfect(t) for t in scene.tracks}
    assert log_problems(scene.tracks, sim) == []
    assert log_problems(scene.tracks, {k: v for k, v in sim.items() if k != "car_001"}) == ["missing car_001"]
    car = sim["car_001"]
    short = SimTrack(car.t[:-2], car.xy[:-2], car.yaw[:-2], car.speed[:-2])
    assert "car_001 logged 0.00-1.40 s, needs 0.00-1.50 s" in log_problems(scene.tracks, {**sim, "car_001": short})
    broken = SimTrack(car.t, car.xy.copy(), car.yaw, car.speed)
    broken.xy[3, 0] = np.nan
    assert log_problems(scene.tracks, {**sim, "car_001": broken}) == ["non-finite values for car_001"]


def test_read_preamble(tmp_path):
    write_log(tmp_path / "log.csv", {"ego": lambda t: (5, 5 * t, 0, 0)}, [0.0])
    assert read_preamble(tmp_path / "log.csv")["esmini GIT TAG"] == "x"


def _perfect(track, offset=0.0):
    t = np.arange(track.t[0], track.t[-1] + 1e-9, 0.05)
    xy = np.column_stack([np.interp(t, track.t, track.xy[:, k]) for k in (0, 1)])
    speed = np.zeros_like(t)
    if len(track.t) > 1:
        seg = np.hypot(*np.diff(track.xy, axis=0).T) / np.diff(track.t)
        speed = seg[np.clip(np.searchsorted(track.t, t, side="right") - 1, 0, len(seg) - 1)]
    return SimTrack(t, xy + [0.0, offset], np.interp(t, track.t, track.yaw), speed)


def test_evaluate(dataroot):
    scene = extract_scene(NuScenesTables(dataroot), "scene-0001")
    perfect = evaluate(scene.tracks, {t.name: _perfect(t) for t in scene.tracks})
    assert perfect["missing"] == []
    assert perfect["summary"]["all"]["max"] == pytest.approx(0, abs=1e-9)
    assert perfect["per_track"]["car_001"]["speed_rmse"] == pytest.approx(0, abs=1e-9)

    shifted = evaluate(scene.tracks, {t.name: _perfect(t, 1.0) for t in scene.tracks[:3]})
    assert shifted["missing"] == ["pedestrian_001"]
    assert shifted["per_track"]["car_001"]["ade"] == pytest.approx(1.0)
    assert shifted["summary"]["moving"]["tracks"] == 2
    assert "ADE" in format_summary(shifted["summary"])


def test_cli_without_esmini(dataroot, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ESMINI_BIN", raising=False)
    monkeypatch.setattr("real2sim.esmini.shutil.which", lambda name: None)
    monkeypatch.setattr("real2sim.esmini.BUNDLED", [])
    code = main(["--dataroot", str(dataroot), "replay", "--scene", "scene-0001", "--out", str(tmp_path / "out"), "--road", "flat"])
    assert code == 2
    out = tmp_path / "out" / "nuscenes-mini" / "scene-0001"  # <out>/<source id>/<scene>/
    for method in ("exact", "baseline", "pilot"):
        assert (out / method / "scene-0001.xosc").is_file() and (out / method / "scene-0001_flat.xodr").is_file()
    assert (out / "tracks_gt.json").is_file()
    assert not list(out.glob("*.new"))  # staged folders swapped in
    assert "4 tracks (2 moving)" in capsys.readouterr().out  # ego and car; the pedestrian moves 0.7 m
