import numpy as np
import pytest

from real2sim.esmini import SimTrack
from real2sim.safety import box_track, braked_poses, corners, dynamics, gap, overlap, pair_measures, side_of
from real2sim.tracks import Scene, Track
from real2sim.variants import (
    assess,
    classify,
    unavoidable_reason,
    grid,
    method_scene,
    other_boxes,
    overlap_times,
    overlapping,
    retime,
    summarize,
    target_box,
    targets,
    variant_scene,
)


def box(x, y, h=0.0, length=4.0, width=2.0):
    return corners(np.array([x, y], float), np.array(h), length, width)


def test_overlap_and_gap():
    assert overlap(box(0, 0), box(1, 0.5))
    assert not overlap(box(0, 0), box(6, 0))
    assert gap(box(0, 0), box(6, 0)) == pytest.approx(2.0)
    assert gap(box(0, 0), box(0, 5)) == pytest.approx(3.0)
    # rotated 45 deg box whose corner points at the other box
    assert not overlap(box(0, 0), box(4.0, 0, np.pi / 4, 2.0, 2.0))
    assert overlap(box(0, 0), box(2.6, 0, np.pi / 4, 2.0, 2.0))


def straight(t, x0, speed, y=0.0):
    return np.column_stack([x0 + speed * t, np.full_like(t, y)])


def test_ttc_constant_velocity():
    t = np.arange(0, 2.01, 0.05)  # boxes would touch at 2.6 s, after the sampled span
    a = box_track(t, straight(t, 0, 10), np.zeros_like(t), 4, 2)
    b = box_track(t, straight(t, 30, 0), np.zeros_like(t), 4, 2)
    m = pair_measures(a, b)
    # centres 30 m apart, boxes touch when 4 m apart: 26 m at 10 m/s
    assert m["ttc"][0] == pytest.approx(2.6, abs=0.11)
    assert m["gap"][0] == pytest.approx(26.0)
    assert not m["overlap"].any()


def test_dynamics():
    t = np.arange(0, 5.01, 0.05)
    assert dynamics(box_track(t, straight(t, 0, 10), np.zeros_like(t), 4, 2))["max_accel"] < 1e-6
    braking = np.column_stack([10 * t - 2 * t**2, 0 * t])  # -4 m/s^2
    d = dynamics(box_track(t, braking, np.zeros_like(t), 4, 2))
    assert d["max_accel"] == pytest.approx(4.0, abs=0.01)
    assert d["max_speed"] == pytest.approx(10.0, abs=0.3)


def car(name, t, xy, category="vehicle.car"):
    return Track(name, category, np.asarray(t, float), np.asarray(xy, float), np.zeros(len(t)), (4.0, 2.0, 1.5))


def test_retime():
    t = np.arange(0, 10.01, 0.1)
    track = car("car_001", t, straight(t, 0, 10))
    fast = retime(track, 1.2, 0.0)
    assert fast.t[-1] == pytest.approx(8.3)  # 1.2 * 10 t <= 100 m
    np.testing.assert_allclose(fast.xy[:, 0], 12 * fast.t, atol=1e-6)
    ahead = retime(track, 1.0, 10.0)
    assert ahead.xy[0, 0] == pytest.approx(10.0) and ahead.t[-1] == pytest.approx(9.0)
    assert retime(track, 1.0, 95.0) is None  # less than 2 s left
    assert len(grid(track)) == (11 * 9 - 1) + 8 * 11 and (1.0, 0.0, 0.0) not in grid(track)


def test_time_shift():
    """Family B: the whole motion 3 s later, cut at the scene end; never outside the recorded path."""
    t = np.arange(0, 10.01, 0.1)
    track = car("car_001", t, straight(t, 0, 10))
    later = retime(track, 1.0, 0.0, 3.0, duration=10.0)
    assert later.t[0] == pytest.approx(3.0) and later.t[-1] == pytest.approx(10.0)
    assert later.xy[0, 0] == pytest.approx(0.0) and later.xy[-1, 0] == pytest.approx(70.0)
    earlier = retime(track, 1.0, 0.0, -3.0, duration=10.0)
    assert earlier.t[0] == pytest.approx(0.0) and earlier.xy[0, 0] == pytest.approx(30.0)
    assert retime(track, 1.0, 0.0, 9.0, duration=10.0) is None  # 1 s left
    walker = Track("pedestrian_001", "human.pedestrian.adult", t, straight(t, 0, 1.2), np.zeros(len(t)), (0.7, 0.7, 1.8))
    offsets = {d for _, d, s in grid(walker) if s == 0}
    assert offsets == set(np.arange(-4.0, 4.1, 1.0)) and len(grid(walker)) == 98 + 88


def scene_with(*tracks):
    return Scene("s", (0.0, 0.0), 10.0, list(tracks))


def as_sim(scene, dt=0.05):
    out = {}
    times = np.arange(0, scene.duration + 1e-9, dt)
    for track in scene.tracks:
        xy = np.column_stack([np.interp(times, track.t, track.xy[:, k]) for k in (0, 1)])
        out[track.name] = SimTrack(times, xy, np.interp(times, track.t, track.yaw), np.zeros_like(times))
    return out


def test_targets_and_assess():
    t = np.arange(0, 10.01, 0.1)
    ego = car("ego", t, straight(t, 0, 5), "vehicle.ego")
    follower = car("car_001", t, straight(t, -40, 8))  # closes in on the ego from behind, 6 m gap left
    parked = car("car_002", t[[0, -1]], [[120, 4], [120, 4]])  # parked off to the side, far ahead
    gt = scene_with(ego, follower, parked)
    assert targets(gt) == ["car_001"]

    sim = as_sim(gt)
    others = other_boxes(gt, gt, sim, "car_001")
    assert set(others) == {"ego", "car_002"}
    original = assess(target_box(gt, sim, "car_001"), others, {})
    assert original["valid"] and original["min_gap_ego"] > 0

    faster = variant_scene(gt, "car_001", 1.4, 0.0)
    row = assess(target_box(faster, as_sim(faster), "car_001"), others, {})
    assert row["valid"]  # overlapping the ego is allowed, it is the system under test
    assert row["min_ttc_ego"] < original["min_ttc_ego"]
    assert row["rare"] == (row["min_ttc_ego"] < 1.5 or row["min_gap_ego"] < 1.0)

    blocked = scene_with(ego, follower, car("car_002", t[[0, -1]], [[20, 0], [20, 0]]))
    sim = as_sim(blocked)
    others = other_boxes(blocked, blocked, sim, "car_001")
    box = target_box(blocked, sim, "car_001")
    assert overlapping(box, others) == {"car_002"}
    row = assess(box, others, {})
    assert "collision" in row["reasons"] and not row["valid"]
    # overlaps already present in the unmodified scenario are excused, but only at those times
    allowed = overlap_times(box, others)
    assert "collision" not in assess(box, others, allowed)["reasons"]
    faster = variant_scene(blocked, "car_001", 1.4, 0.0)
    moved = assess(target_box(faster, as_sim(faster), "car_001"), others, allowed)
    assert "collision" in moved["reasons"]  # reaches the parked car earlier than in the original
    assert assess(None, others, {})["reasons"] == ["missing_in_log"]


def test_method_scene_replays_the_recorded_ego():
    """Audit 1.1: the ego must be the same (the recording) for baseline and pilot."""
    rng = np.random.default_rng(3)
    t = np.arange(0, 10.01, 0.5)
    ego = car("ego", t, straight(t, 0, 5) + rng.normal(0, 0.2, (len(t), 2)), "vehicle.ego")
    other = car("car_001", t, straight(t, -30, 8, 3.5) + rng.normal(0, 0.2, (len(t), 2)))
    gt = scene_with(ego, other)
    for method in ("baseline", "pilot"):
        scene = method_scene(gt, method)
        assert scene.tracks[0] is ego
        assert len(scene.tracks[1].t) > len(t)  # the other objects are reconstructed (0.1 s vertices)


def test_side_of():
    t = np.array([0.0, 1.0])
    still = lambda x, y, h=0.0: box_track(t, [[x, y], [x, y]], [h, h], 4, 2)  # noqa: E731
    ego = still(0, 0)
    assert [side_of(still(*p), ego, 0.5) for p in ((10, 1), (-10, -1), (1, 5), (1, -5))] == \
        ["front", "rear", "left", "right"]
    north = still(0, 0, np.pi / 2)  # heading north: east is on its right
    assert side_of(still(10, 0), north, 0.5) == "right"


def test_ego_overlap_counts_even_when_the_recording_overlaps():
    """Audit 2.3: a near miss means no box overlap with the ego at all, excused times included."""
    t = np.arange(0, 5.01, 0.1)
    ego = box_track(t, straight(t, 0, 5), np.zeros_like(t), 4, 2)
    behind = box_track(t, straight(t, -3, 5), np.zeros_like(t), 4, 2)  # overlaps the ego the whole time
    row = assess(behind, {"ego": ego}, {"ego": t})
    assert row["valid"] and row["ego_collision"] and row["min_gap_ego"] == 0
    assert row["conflict"] == "rear"
    near = box_track(t, straight(t, -4.5, 5), np.zeros_like(t), 4, 2)  # 0.5 m behind
    row = assess(near, {"ego": ego}, {})
    assert row["rare"] and not row["ego_collision"] and row["min_gap_ego"] == pytest.approx(0.5)


def test_braked_poses():
    """v(t) = min(v_rec, v_brake - a (t - t_brake)), never below 0, never ahead of the recording."""
    t = np.arange(0, 6.001, 0.05)
    cruise = box_track(t, straight(t, 0, 10), np.zeros_like(t), 4, 2)
    centre, _ = braked_poses(cruise, 1.0, np.array([5.0, 10.0]))
    assert centre[0, -1, 0] == pytest.approx(10 + 10, abs=0.05)  # 10 m to t=1, then 10^2 / (2*5)
    assert centre[1, -1, 0] == pytest.approx(10 + 5, abs=0.05)
    np.testing.assert_allclose(centre[:, t <= 1.0, 0], np.tile(10 * t[t <= 1.0], (2, 1)), atol=1e-9)
    slowing = box_track(t, np.column_stack([10 * t - t**2, 0 * t]), np.zeros_like(t), 4, 2)  # -2 m/s^2
    centre, _ = braked_poses(slowing, 1.0, np.array([1.0]))  # gentler than the recording: follows it
    np.testing.assert_allclose(centre[0, :, 0], slowing.centre[:, 0], atol=0.02)


def _ego_and(actor_xy, actor_t, ego_speed, ego_t=np.arange(0, 8.001, 0.05)):
    ego = box_track(ego_t, straight(ego_t, 0, ego_speed), np.zeros_like(ego_t), 4.0, 2.0, 1.39)
    actor = box_track(actor_t, actor_xy, np.zeros_like(actor_t), 4.0, 2.0)
    return ego, actor


def test_groups_from_braking():
    """Section 10.4-10.6: mild / hard / unavoidable / late, each worked out by hand."""
    t = np.arange(0, 8.001, 0.05)
    # lead at 2 m/s, 40 m ahead of a 15 m/s ego: TTC 2.7 s at once, braking from 1.0 s with 21.6 m
    # left at 13 m/s closing speed needs 13^2 / (2 * 21.6) = 3.9 m/s^2: hard
    ego, lead = _ego_and(straight(t, 40, 2), t, 15)
    row = assess(lead, {"ego": ego}, {})
    assert row["crash"] and row["presence_s"] >= 2
    assert row["braking"]["r1.0_d3.0"]["a_need"] == pytest.approx(4.0)
    assert row["group"] == "hard" and row["valuable"] and row["conflict"] == "front"
    assert classify(row, {"reaction_s": 0.5}) == "mild" or row["braking"]["r0.5_d3.0"]["a_need"] > 3.4

    # a faster car from behind: braking only makes it worse
    ego, chaser = _ego_and(straight(t, -20, 10), t, 5)
    row = assess(chaser, {"ego": ego}, {})
    assert row["crash"] and row["conflict"] == "rear" and row["group"] == "unavoidable"
    assert unavoidable_reason(row) == "no_decel" and not row["valuable"]

    # on a bend the straight-line TTC misses the conflict; the range TTC (gap / closing rate) does not
    arc = np.linspace(0, np.pi / 3, len(t))
    ego_xy = 60 * np.column_stack([np.sin(arc), 1 - np.cos(arc)])  # 60 m radius, ~7.9 m/s
    ego = box_track(t, ego_xy, arc + 0.0, 4.0, 2.0, 1.39)
    s_lead = 30 + 3 * t  # 3 m/s, ahead on the same bend; the ego reaches it after about 5 s
    lead_xy = 60 * np.column_stack([np.sin(s_lead / 60), 1 - np.cos(s_lead / 60)])
    lead = box_track(t, lead_xy, s_lead / 60, 4.0, 2.0)
    row = assess(lead, {"ego": ego}, {})
    entry = row["braking"]["r1.0_d3.0"]
    assert row["crash"] and entry["detected_by"] == "path"
    assert entry["t_detect"] <= row["critical_t"] - 2.5
    assert row["group"] in ("mild", "hard")

    # a cut-in is not foreseen: a slower car in the next lane (3.5 m) swerves in smoothly from 4.0 s;
    # it is detected only once it moves sideways (4.2 s), the crash comes at 4.8 s: no time to react
    u = np.clip((t - 4.0) / 1.6, 0, 1)
    ego, cutter = _ego_and(np.column_stack([12 * t + 14, 3.5 * (1 + np.cos(np.pi * u)) / 2]), t, 15)
    row = assess(cutter, {"ego": ego}, {})
    entry = row["braking"]["r1.0_d3.0"]
    assert row["valid"] and row["crash"] and entry["t_detect"] >= 4.0
    assert row["group"] == "unavoidable" and entry["reason"] == "reaction"

    # the same lead car, but present only from 1 s before the crash: late
    late_t = t[t >= 1.7]
    ego, lead = _ego_and(straight(late_t, 40, 2), late_t, 15)
    assert assess(lead, {"ego": ego}, {})["group"] == "late"


def test_pedestrian_may_touch_pedestrians():
    """Owner decision 12/10/2026: people walking side by side step around each other."""
    t = np.arange(0, 5.001, 0.1)
    walk = lambda y: box_track(t, straight(t, 0, 1.2, y), np.zeros_like(t), 0.7, 0.7)  # noqa: E731
    me, friend, car_ = walk(0.0), walk(0.5), box_track(t, straight(t, 0.3, 1.2, 0.0), np.zeros_like(t), 4, 2)
    row = assess(me, {"pedestrian_002": friend}, {}, (3.0, 3.0), frozenset({"pedestrian_002"}))
    assert row["valid"] and row["soft_contacts"] == ["pedestrian_002"] and row["collisions"] == []
    row = assess(me, {"pedestrian_002": friend, "car_001": car_}, {}, (3.0, 3.0), frozenset({"pedestrian_002"}))
    assert not row["valid"] and row["collisions"] == ["car_001"]
    assert not assess(me, {"pedestrian_002": friend}, {}, (3.0, 3.0))["valid"]  # not soft: a collision


def test_pop_in_and_out_near_the_ego():
    """Owner decision 12/10/2026: no actor appears or vanishes in the road next to the ego (< 20 m)."""
    t = np.arange(0, 10.001, 0.05)
    ego = box_track(t, straight(t, 0, 5), np.zeros_like(t), 4.0, 2.0, 1.39)
    late = t[t >= 3.0]
    near = box_track(late, straight(late, 30, 2), np.zeros_like(late), 4.0, 2.0)  # appears 8.6 m ahead at 3 s
    row = assess(near, {"ego": ego}, {}, duration=10.0)
    assert not row["valid"] and "pop_in" in row["reasons"]
    far = box_track(late, straight(late, 60, 2), np.zeros_like(late), 4.0, 2.0)  # 38.6 m ahead: like a real label
    assert "pop_in" not in assess(far, {"ego": ego}, {}, duration=10.0)["reasons"]
    from_start = box_track(t, straight(t, 30, 2), np.zeros_like(t), 4.0, 2.0)  # there from 0 s: fine
    assert "pop_in" not in assess(from_start, {"ego": ego}, {}, duration=10.0)["reasons"]
    early_end = t[t <= 6.0]
    gone = box_track(early_end, straight(early_end, 30, 2), np.zeros_like(early_end), 4.0, 2.0)
    assert "pop_out" in assess(gone, {"ego": ego}, {}, duration=10.0)["reasons"]
    assert assess(gone, {"ego": ego}, {})["valid"]  # no duration given: not checked


def test_excused_ego_overlap_is_not_a_crash():
    t = np.arange(0, 5.001, 0.1)
    ego, beside = _ego_and(straight(t, 0, 5, 1.5), t, 5)  # overlaps the ego the whole time
    row = assess(beside, {"ego": ego}, {"ego": t})  # ... and so does the recording
    assert not row["crash"] and row["excused_overlap"]
    assert row["group"] == "late"  # close, but its closest moment is at t = 0, when it appears
    assert assess(beside, {"ego": ego}, {})["crash"]  # without the recording's overlap it is a crash


def test_classify_thresholds():
    braking = {"r1.0_d3.0": {"a_need": 5.0, "reason": None}, "r2.5_d3.0": {"a_need": None, "reason": "reaction"}}
    row = {"valid": True, "crash": True, "presence_s": 2.5, "braking": braking}
    assert classify(row) == "hard"
    assert classify(row, {"comfort_decel": 6.0}) == "mild"
    assert classify(row, {"max_decel": 4.0}) == "unavoidable"
    assert classify(row, {"reaction_s": 2.5}) == "unavoidable"
    assert classify(row, {"min_presence_s": 3.0}) == "late"
    near = {"valid": True, "crash": False, "presence_s": 4.0, "min_ttc_ego": 1.8, "min_gap_ego": 2.0}
    assert classify(near) == "far" and classify(near, {"close_ttc_s": 2.0}) == "close"
    assert classify({**near, "valid": False}) is None


def _row(target, conflict, rare=True, collision=False, **extra):
    gap = 0.5 if rare else 5.0
    return {"target": target, "actor": "vehicle", "valid": rare, "rare": rare, "reasons": [],
            "ego_collision": collision, "crash": False, "excused_overlap": False, "conflict": conflict,
            "min_ttc_ego": float("inf"), "min_gap_ego": gap, "presence_s": 5.0, **extra}


def test_summarize_counts_distinct_events():
    """Audit 1.2/1.3: many variants of one actor are one event; the recording is counted in events."""
    rows = [_row("car_001", "rear"), _row("car_001", "rear", collision=True), _row("car_001", "left"),
            _row("car_002", "front", kept=True), _row("car_003", None, rare=False),
            {"target": "car_003", "valid": False, "rare": False, "reasons": ["span"]},
            {**_row("car_004", "front", rare=False), "valid": False, "reasons": ["full_replay"]}]
    original = {name: {"valid": True} for name in ("car_001", "car_002", "car_003", "car_004")}
    recorded = {"car_001": {"target": "car_001", "actor": "vehicle", "valid": False, "crash": False,
                            "min_ttc_ego": 1.0, "min_gap_ego": 3.0, "conflict": "rear", "presence_s": 5.0},
                "car_002": {"target": "car_002", "actor": "vehicle", "valid": True, "crash": False,
                            "min_ttc_ego": 9.0, "min_gap_ego": 3.0, "conflict": "front", "presence_s": 5.0}}
    s = summarize(rows, original, recorded)
    assert (s["generated"], s["written"], s["valid"], s["rare"]) == (7, 6, 4, 4)
    assert s["rare_near_miss"] == 3
    assert (s["rare_targets"], s["rare_events"]) == (2, 3)
    assert s["recorded_rare_events"] == 1  # car_001 from the rear is already in the recording
    assert s["new_rare_events"] == 2
    assert (s["kept_xosc"], s["full_replay_failed"]) == (1, 1)
