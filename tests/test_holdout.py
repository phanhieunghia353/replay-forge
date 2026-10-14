"""Held-out check of metric 1 (real2sim/holdout.py)."""

import numpy as np
import pytest

from real2sim.holdout import holdout_scene, split
from real2sim.tracks import Scene, Track

T = np.arange(0, 10.01, 0.5)


def test_split_keeps_ends_and_hides_every_other_label():
    track = Track("car_001", "vehicle.car", T, np.column_stack([3 * T, 0 * T]), 0 * T, (4.0, 2.0, 1.5))
    kept, hidden = split(track)
    assert kept.t[0] == 0 and kept.t[-1] == 10.0 and list(hidden) == list(range(1, 20, 2))


def test_errors_are_measured_on_hidden_labels_only():
    """A car speeding up: straight lines between the kept labels miss the hidden ones a little, one
    constant speed misses them a lot; a parked car is left out."""
    x = 0.5 * T ** 2
    moving = Track("car_001", "vehicle.car", T, np.column_stack([x, 0 * T]), 0 * T, (4.0, 2.0, 1.5))
    parked = Track("car_002", "vehicle.car", T, np.full((len(T), 2), 50.0), 0 * T, (4.0, 2.0, 1.5))
    result = holdout_scene(Scene("s", (0.0, 0.0), 10.0, [moving, parked]))
    assert result["tracks"] == 1 and set(result["per_track"]) == {"car_001"}
    s = result["summary"]
    assert s["exact"] == pytest.approx(0.125, abs=1e-6)  # midpoint of a parabola over 1 s: 0.5 * 0.5^2 / 2
    assert s["baseline"] > 5 * s["exact"] and s["pilot"] < s["baseline"]


def test_straight_lines_through_noisy_labels_jerk_and_the_pilot_does_not():
    rng = np.random.default_rng(3)
    noisy = np.column_stack([10 * T + rng.normal(0, 0.2, len(T)), rng.normal(0, 0.2, len(T))])
    car = Track("car_001", "vehicle.car", T, noisy, 0 * T, (4.0, 2.0, 1.5))
    peaks = holdout_scene(Scene("s", (0.0, 0.0), 10.0, [car]))["smoothness"]
    assert peaks["exact"]["car_001"] > 4.0 > peaks["pilot"]["car_001"]
