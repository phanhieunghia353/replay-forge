import math

import numpy as np
import pytest

from real2sim.abstraction import KNOT_SPACING, baseline, pilot, reconstruct, smooth_path
from real2sim.nuscenes_io import NuScenesTables
from real2sim.tracks import Track, extract_scene


def make_track(t, xy, yaw=None):
    t = np.asarray(t, float)
    yaw = np.zeros(len(t)) if yaw is None else np.asarray(yaw, float)
    return Track("car_001", "vehicle.car", t, np.asarray(xy, float), yaw, (4.5, 1.9, 1.6))


def test_baseline_constant_speed():
    track = make_track([0, 1, 2, 3], [[0, 0], [1, 0], [4, 0], [9, 0]])  # accelerating
    out = baseline(track)
    assert out.t[0] == 0 and out.t[-1] == 3
    np.testing.assert_allclose(np.diff(out.t), 0.1, atol=1e-9)
    assert np.interp(1.5, out.t, out.xy[:, 0]) == pytest.approx(4.5)  # 9 m in 3 s at constant speed
    assert out.xy[-1] == pytest.approx([9, 0])


def test_pilot_pins_stationary_track():
    rng = np.random.default_rng(0)
    t = np.arange(0, 6.01, 0.5)
    xy = np.array([30.0, 10.0]) + rng.normal(0, 0.15, (len(t), 2))
    out = pilot(make_track(t, xy, np.full(len(t), 0.3)))
    assert out.is_static and list(out.t) == [0, 6]  # one pose, kept over the annotated span
    assert out.xy[0] == pytest.approx(xy.mean(axis=0))
    assert out.yaw[0] == pytest.approx(0.3)


def test_pilot_smoothing_beats_raw_on_noisy_line():
    rng = np.random.default_rng(1)
    t = np.arange(0, 12.01, 0.5)
    truth = np.column_stack([10 * t, np.zeros_like(t)])
    noisy = truth + rng.normal(0, 0.15, truth.shape)
    out = pilot(make_track(t, noisy))
    est = np.column_stack([np.interp(t, out.t, out.xy[:, k]) for k in (0, 1)])
    assert np.hypot(*(est - truth).T).mean() < np.hypot(*(noisy - truth).T).mean()


def test_pilot_speed_knots():
    t = np.arange(0, 12.01, 0.5)
    x = np.where(t < 6, 10 * t, 60 + 4 * (t - 6))  # 10 m/s, then 4 m/s
    out = pilot(make_track(t, np.column_stack([x, np.zeros_like(t)])))
    speed = np.diff(out.xy[:, 0]) / np.diff(out.t)
    assert (speed >= -1e-9).all()
    # knots every KNOT_SPACING seconds keep the travelled distance
    for knot in np.arange(0, 12, KNOT_SPACING):
        assert np.interp(knot, out.t, out.xy[:, 0]) == pytest.approx(np.interp(knot, t, x), abs=0.3)
    # speed is continuous: no jump larger than a hard brake over one 0.1 s step
    assert np.abs(np.diff(speed)).max() < 1.0
    assert speed[out.t[:-1] < 4].mean() == pytest.approx(10, abs=0.3)
    assert speed[out.t[:-1] > 8].mean() == pytest.approx(4, abs=0.3)


def test_heading_follows_motion_and_reversing():
    t = np.arange(0, 6.01, 0.5)
    forward = smooth_path(make_track(t, np.column_stack([5 * t, 0 * t]), np.zeros_like(t)))
    assert np.abs(forward[2]).max() < 1e-3
    # box faces east (yaw 0) while driving west: reversing, heading must stay at the box yaw
    reverse = smooth_path(make_track(t, np.column_stack([-2 * t, 0 * t]), np.zeros_like(t)))
    assert np.abs(reverse[2]).max() < 1e-3
    north = smooth_path(make_track(t, np.column_stack([0 * t, 5 * t]), np.full_like(t, 1.5)))
    assert north[2] == pytest.approx(np.full_like(north[2], math.pi / 2), abs=1e-3)


def test_short_track_falls_back_to_linear():
    out = pilot(make_track([1.0, 1.5], [[10, 6], [14, 6]]))
    assert out.t[0] == 1.0 and out.t[-1] == 1.5
    assert out.xy[-1] == pytest.approx([14, 6])


def test_reconstruct_scene(dataroot):
    scene = extract_scene(NuScenesTables(dataroot), "scene-0001")
    assert reconstruct(scene, "exact").tracks[2] is scene.tracks[2]
    names = [track.name for track in reconstruct(scene, "pilot").tracks]
    assert names == [track.name for track in scene.tracks]
    with pytest.raises(ValueError):
        reconstruct(scene, "nope")
