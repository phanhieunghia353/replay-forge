"""Stage 1 behaviour simulation (docs/thiet-ke-kich-ban-hanh-vi.md, section 4) on hand-made scenes."""

import math

import numpy as np
import pytest

from real2sim import behavior, events
from real2sim.behavior import DT, REACTION, Event, SceneModel, find_leader, outline, simulate
from real2sim.tracks import Scene, Track

T = np.arange(0, 20.001, 0.5)  # 2 Hz keyframes, like nuScenes


def car(name, xy, t=T, size=(4.5, 1.9, 1.6), category="vehicle.car", yaw=0.0):
    xy = np.asarray(xy, float)
    return Track(name, category, np.asarray(t, float), xy, np.full(len(t), yaw), size,
                 bbox_center_x=1.39 if name == "ego" else 0.0)


def lane(x0, speed, t=T, y=0.0):
    return np.column_stack([x0 + speed * t, np.full(len(t), y)])


def queue_scene(*extra):
    """ego far away in another lane; car_001 leads car_002 by 30 m (centre to centre) at 10 m/s."""
    ego = car("ego", lane(-200, 5, y=40.0), category="vehicle.ego", size=(4.084, 1.73, 1.562))
    return Scene("q", (0.0, 0.0), 20.0, [ego, car("car_001", lane(30, 10)), car("car_002", lane(0, 10)), *extra])


def test_no_event_is_the_recording():
    m = SceneModel(queue_scene())
    out = simulate(m, Event("car_001", 99.0, 4.0, "stop"), react=True)  # never starts
    assert not out.changed.any()
    np.testing.assert_array_equal(np.isnan(out.S), np.isnan(m.S))
    np.testing.assert_allclose(out.S[~np.isnan(m.S)], m.S[~np.isnan(m.S)])


def test_follower_reacts_after_the_reaction_time_and_stops_behind():
    m = SceneModel(queue_scene())
    f = m.index["car_002"]
    assert m.leader[100, f] == m.index["car_001"]
    assert m.agents[f].T == pytest.approx(2.5)  # 25.5 m bumper gap at 10 m/s, clipped to 2.5 s
    out = simulate(m, Event("car_001", 2.0, 4.0, "stop", dwell=99.0), react=True)
    seen, drives = out.stimulus["car_002"], out.driving_from["car_002"]
    assert 2.0 < seen < 2.6  # once its leader is 0.3 m/s below its plan (braking builds up at 10 m/s^3)
    assert drives - seen == pytest.approx(REACTION, abs=DT + 1e-9)
    # nominal until it reacts, then it stops behind the stopped leader, at about its standstill gap
    k_react = int(round(drives / DT))
    np.testing.assert_allclose(out.S[:k_react, f], m.S[:k_react, f])
    X, Y, H = behavior.centres(m, out)
    gap = X[-1, m.index["car_001"]] - X[-1, f] - 4.5
    assert out.V[-1, f] == pytest.approx(0.0, abs=0.05)  # IDM creeps up to its standstill gap
    assert m.agents[f].s0 - 0.3 < gap < m.agents[f].s0 + 1.0
    assert not events.assess(m, out).collisions


def test_without_reactions_the_follower_runs_into_it():
    m = SceneModel(queue_scene())
    base = events.assess(m, simulate(m, Event("car_001", 2.0, 4.0, "stop", dwell=99.0), react=False))
    assert "collision" in base.reasons and not base.valid
    pilot = events.assess(m, simulate(m, Event("car_001", 2.0, 4.0, "stop", dwell=99.0), react=True))
    assert pilot.valid


def test_speed_never_negative_and_no_overshoot_when_stopping():
    m = SceneModel(queue_scene())
    out = simulate(m, Event("car_001", 2.0, 8.0, "stop", dwell=99.0), react=True)
    for name in ("car_001", "car_002"):
        i = m.index[name]
        s = out.S[:, i][~np.isnan(out.S[:, i])]
        assert (np.diff(s) >= -1e-9).all() and np.nanmin(out.V[:, i]) >= 0.0


def test_event_vehicle_resumes_its_plan_with_the_recorded_dwell_time():
    """car_001 in the recording stops 3 s at x = 110 (from 8 s to 11 s). Halved at 1 s, it reaches that
    point later, still waits about 3 s there, and does not hurry to make up the delay."""
    speed = np.where(T < 8, 10.0, np.where(T < 11, 0.0, 10.0))
    x = np.concatenate([[30.0], 30 + np.cumsum(0.5 * (speed[1:] + speed[:-1]) / 2)])
    m = SceneModel(Scene("q", (0.0, 0.0), 20.0, [queue_scene().tracks[0], car("car_001", np.column_stack([x, 0 * x]))]))
    i = m.index["car_001"]
    assert len(m.agents[i].stops) == 1
    s_star, ks, ke = m.agents[i].stops[0]
    planned = (ke - ks + 1) * DT  # the dwell of the (smoothed) plan
    assert planned >= 1.0  # pilot's 2 s speed knots shorten the recorded 3 s stop (found 13/10/2026: 1.55 s)
    out = simulate(m, Event("car_001", 1.0, 2.0, "half"), react=True)
    v, s = out.V[:, i], out.S[:, i]
    waiting = (~np.isnan(v)) & (v < 0.05) & (np.abs(s - s_star) < behavior.STOP_REACH)
    assert waiting.sum() * DT == pytest.approx(planned, abs=0.3)
    assert np.flatnonzero(waiting)[0] > ks  # it gets there later than planned
    assert np.nanmax(v) <= np.nanmax(m.V[:, i]) + 0.2  # never faster than its plan


def test_enhanced_idm_does_not_brake_hard_for_a_leader_pulling_away():
    """10 m/s, 5 m behind a leader at 10.5 m/s: the plain IDM brakes about 8.7 m/s^2 (desired gap
    2 + 12 - 10 * 0.5 / (2 * sqrt(1.5 * 2)) = 12.6 m); the leader pulls away, so the enhanced IDM
    brakes no harder than the comfortable b. A stopped obstacle 20 m ahead needs about
    v^2 / (2 g) = 2.5 m/s^2 and gets at least that."""
    term, a = behavior.enhanced_idm(10.0, 12.0, 5.0, 10.5, 0.0, 2.0, 1.2)
    plain = behavior.IDM_A * (1 - (10 / 12) ** 4 - term)
    assert plain == pytest.approx(-8.7, abs=0.1)
    assert -behavior.IDM_B - 0.1 < a < 0
    _, a_stop = behavior.enhanced_idm(10.0, 12.0, 20.0, 0.0, 0.0, 2.0, 1.2)
    assert a_stop <= -10.0 ** 2 / (2 * 20.0) + 1e-6


def test_result_does_not_depend_on_agent_order():
    scene = queue_scene(car("car_003", lane(-30, 10)))
    m1 = SceneModel(scene)
    flipped = Scene(scene.name, scene.origin, scene.duration, [scene.tracks[0], *scene.tracks[1:][::-1]])
    m2 = SceneModel(flipped)
    o1 = simulate(m1, Event("car_001", 2.0, 6.0, "stop", 3.0))
    o2 = simulate(m2, Event("car_001", 2.0, 6.0, "stop", 3.0))
    for name in ("car_001", "car_002", "car_003"):
        np.testing.assert_allclose(o1.S[:, m1.index[name]], o2.S[:, m2.index[name]], equal_nan=True)


def test_leader_is_found_by_the_box_not_the_centre():
    """A 14 m bus stopped at 60 degrees across the lane, its centre 5 m to the side: it blocks the path.
    A car alongside (not ahead) is not a leader."""
    bus = car("bus_001", np.array([[40.0, 5.0]] * len(T)), size=(14.0, 3.0, 3.0), category="vehicle.bus.rigid",
              yaw=math.radians(60))
    side = car("car_009", lane(1.0, 10, y=1.2), size=(1.8, 0.7, 1.5), category="vehicle.bicycle")
    m = SceneModel(queue_scene(bus, side))
    f = m.index["car_002"]
    k = 0
    cx, cy, ch, cv = m.X[k], m.Y[k], m.H[k], m.V[k]
    j, g = find_leader(m, f, m.S[k, f], cx, cy, ch, cv, m.present[k])
    assert m.agents[j].name == "car_001"  # the bicycle beside it does not count
    pts = outline(40.0, 5.0, math.radians(60), 14.0, 3.0)
    assert (np.abs(pts[:, 1]) < 1.0).any()  # the outline crosses the lane although the centre is 5 m off
    gone = Scene("q", (0.0, 0.0), 20.0, [queue_scene().tracks[0], car("car_002", lane(0, 10)), bus])
    m = SceneModel(gone)
    f = m.index["car_002"]
    j, g = find_leader(m, f, m.S[0, f], m.X[0], m.Y[0], m.H[0], m.V[0], m.present[0])
    assert m.agents[j].name == "bus_001" and 20 < g < 40


def test_candidates_need_a_follower_and_time():
    m = SceneModel(queue_scene())
    found = events.candidates(m)
    assert {e.actor for e in found} == {"car_001"}  # car_002 has nobody behind it
    assert len({(e.decel, e.target, e.dwell) for e in found}) == len(events.DECELS) * len(events.TARGETS)
    assert max(e.t0 for e in found) < 20.0 - events.AFTER_EVENT


def test_a_driver_who_must_brake_takes_the_foot_off_the_throttle_first():
    # accelerating at 4 m/s^2 and needing to brake: the drive force goes at once, braking builds from zero
    assert behavior._jerk_limited(4.0, -8.0) == pytest.approx(-behavior.JERK_BRAKE * DT)
    assert behavior._jerk_limited(4.0, 1.0) == pytest.approx(4.0 - behavior.JERK_BRAKE * DT)  # easing off: smooth
    assert behavior._jerk_limited(-2.0, -8.0) == pytest.approx(-2.0 - behavior.JERK_BRAKE * DT)


def test_buses_and_trucks_brake_less_hard_than_cars():
    bus = car("bus_001", lane(0, 10), size=(12.0, 2.6, 3.2), category="vehicle.bus.rigid")
    ego = queue_scene().tracks[0]
    m = SceneModel(Scene("q", (0.0, 0.0), 20.0, [ego, car("car_001", lane(30, 10)), bus]))
    b = m.index["bus_001"]
    assert m.agents[b].max_decel == behavior.HEAVY_MAX_DECEL < behavior.MAX_DECEL
    assert m.agents[m.index["car_001"]].max_decel == behavior.MAX_DECEL
    out = simulate(m, Event("car_001", 2.0, 8.0, "stop", dwell=99.0), react=True)
    assert np.nanmin(out.A[:, b]) >= -behavior.HEAVY_MAX_DECEL - 1e-9
    # and a bus is never asked to brake harder than it can as the event vehicle
    m2 = SceneModel(Scene("q", (0.0, 0.0), 20.0, [ego, car("bus_002", lane(30, 10), size=(12.0, 2.6, 3.2),
                                                          category="vehicle.bus.rigid"), car("car_002", lane(0, 10))]))
    decels = {e.decel for e in events.candidates(m2) if e.actor == "bus_002"}
    assert decels and max(decels) <= behavior.HEAVY_MAX_DECEL


def test_a_jump_in_the_recorded_labels_is_reported_as_a_label_error():
    """car_001's labels jump 20 m forward at 12 s (a labelling error). Replayed 1 s late (as a delayed vehicle
    is), the jump is still there at the same place on its path: invalid, but the data is to blame."""
    x = 30 + 10 * T + np.where(T >= 12, 20.0, 0.0)
    m = SceneModel(Scene("q", (0.0, 0.0), 20.0, [queue_scene().tracks[0], car("car_001", np.column_stack([x, 0 * x])),
                                                 car("car_002", lane(0, 10))]))
    i, lag = m.index["car_001"], int(round(1.0 / DT))
    assert len(events._physics_violations(m.X, m.Y, i, behavior.MAX_DECEL))  # the recording itself breaks the limits
    S, V = m.S.copy(), m.V.copy()
    S[lag:, i], V[lag:, i] = m.S[:-lag, i], m.V[:-lag, i]
    S[:lag, i] = V[:lag, i] = np.nan  # enters 1 s late, already moving
    changed = np.zeros(len(m.agents), bool)
    changed[i] = True
    late = behavior.Outcome(Event("car_001", 0.0, 2.0, "stop"), True, S, V, np.zeros_like(S), changed, {}, {}, {})
    a = events.assess(m, late)
    assert "label_error" in a.reasons and "physics" not in a.reasons and not a.valid
    # a jump the recording does not have is the variant's fault
    S2 = m.S.copy()
    S2[200:, m.index["car_002"]] += 15.0
    changed2 = np.zeros(len(m.agents), bool)
    changed2[m.index["car_002"]] = True
    jumpy = behavior.Outcome(Event("car_001", 0.0, 2.0, "stop"), True, S2, m.V.copy(), np.zeros_like(S2), changed2,
                             {}, {}, {})
    assert "physics" in events.assess(m, jumpy).reasons


def test_a_vehicle_merging_in_is_not_counted_as_following():
    K = 100
    H = np.zeros((K, 2))
    H[:, 1] = np.linspace(math.radians(70), 0.0, K)  # turns in from a side road, aligned at the end
    assert events._merging(H, K - 1, 0, 1)
    H[:, 1] = math.radians(5)
    assert not events._merging(H, K - 1, 0, 1)
    H[:, 1] = math.pi - math.radians(5)  # opposite direction, aligned
    assert not events._merging(H, K - 1, 0, 1)


def test_passing_a_slowed_car_in_the_next_lane_is_not_a_near_miss():
    """car_001 brakes, car_002 behind it stops; the ego drives on in the next lane (2,6 m to the side) and
    passes car_002 about 0,8 m away. Normal traffic, not a near miss: the distance rule only counts in front
    of or behind the ego."""
    ego = car("ego", lane(-20, 10, y=2.6), category="vehicle.ego", size=(4.084, 1.73, 1.562))
    m = SceneModel(Scene("q", (0.0, 0.0), 20.0, [ego, car("car_001", lane(30, 10)), car("car_002", lane(0, 10))]))
    a = events.assess(m, simulate(m, Event("car_001", 2.0, 6.0, "stop", dwell=99.0), react=True))
    assert a.valid and a.ego["min_gap"] < events.CLOSE_GAP  # the boxes do come within 1 m ...
    assert a.ego["min_gap_path"] is None and a.group != "close"  # ... but beside it, never on its path
    assert a.ego["conflict_side"] in ("left", "right")


def test_on_path_and_sides():
    from real2sim.safety import box_track

    t = np.arange(0, 2.01, 0.5)
    ego = box_track(t, np.column_stack([10 * t, 0 * t]), 0 * t, 4.0, 1.8)
    ahead = box_track(t, np.column_stack([10 * t + 5.0, 0 * t]), 0 * t, 4.0, 1.8)
    beside = box_track(t, np.column_stack([10 * t + 1.0, 0 * t + 2.6]), 0 * t, 4.0, 1.8)
    behind = box_track(t, np.column_stack([10 * t - 5.0, 0 * t - 0.3]), 0 * t, 4.0, 1.8)
    assert events._on_path(ahead, ego, t).all() and events._on_path(behind, ego, t).all()
    assert not events._on_path(beside, ego, t).any()
    assert [events._side(b, ego, 1.0) for b in (ahead, beside, behind)] == ["front", "left", "rear"]
