"""Variants of one actor, replayed in esmini, checked for validity and criticality.

Two families of variants (docs/gia-dinh-va-chi-so.md, section 10.3):
  A  speed x offset   s'(t) = factor * s(t) + offset, s(t) the distance travelled along the path at time t;
                      factor > 1 drives faster, offset > 0 puts the actor further ahead along its own path
  B  time x speed     the same with offset 0, and the whole motion happening `shift` seconds later (< 0: earlier)
Only times with 0 <= s' <= path length and 0 <= t + shift <= scene duration are kept, so no motion outside
the recorded path is invented. Actors: every moving vehicle, two-wheeler and pedestrian except the ego.

The scene a variant starts from (method_scene) has every object reconstructed by the method under
test, except the ego, which replays its recording in every method: it stands for the system under
test and must be the same for baseline and pilot.

Each variant is checked by replaying only the actor and the ego in esmini; every other object is
unchanged, so its replayed motion is taken from one full replay of the unmodified scenario. Variants
that are kept as deliverables are written with the whole scene and replayed again in full; a kept
variant whose full replay fails is not valid (reason "full_replay").

Validity (all must hold):
  esmini      the run ends with exit code 0 and the log covers the actor and the ego over their spans
  span        at least MIN_VARIANT_SPAN seconds of the variant remain
  dynamics    peak speed and peak acceleration within the limits of the actor's type (LIMITS)
  collisions  the actor's box does not overlap any object other than the ego, except at the times
              (within ALLOWED_DT) when it overlaps that object in the recorded scenario
Overlap with the ego is allowed: the ego stands for the system under test.

Criticality, version 2 (section 10.4-10.6), for a valid variant:
  (a) if the ego does not react: "crash" (box overlap with the ego at a time the recording does not
      overlap it), else "close" (TTC < CLOSE_TTC or gap < CLOSE_GAP), else "far"
  (b) crash only: the reference driver detects the actor when TTC first drops below DETECT_TTC, brakes
      REACTION seconds later along the recorded path, v = min(v_rec, v_brake - a t); a_need is the
      smallest a on DECELS that avoids every overlap from then on (grid search: avoidance need not
      grow with a at a junction)
  groups: far | close | mild (a_need <= COMFORT_DECEL) | hard (<= MAX_DECEL) | unavoidable | late
          (actor present < MIN_PRESENCE before the critical moment); "valuable" = close or hard.
Version 1 ("rare": TTC < CLOSE_TTC or gap < CLOSE_GAP) is kept next to it for comparison.

Event: (actor, actor type / side of the ego at the critical moment). Many variants of one actor are
often the same event; counts of distinct events sit next to counts of files, and the recorded
scenario is counted in events too.
"""

from __future__ import annotations

import itertools

import numpy as np

from real2sim.abstraction import arc_length, drive_along, reconstruct, with_poses
from real2sim.esmini import SimTrack
from real2sim.safety import BoxTrack, box_track, braking_avoids, dynamics, pair_measures, path_ttc, side_of
from real2sim.tracks import Scene, Track

# ---------------------------------------------------------------- grid
SPEED_FACTORS = tuple(round(0.5 + 0.1 * k, 1) for k in range(11))  # 0.5 .. 1.5
OFFSETS = tuple(-10.0 + 2.5 * k for k in range(9))  # -10 .. +10 m along the actor's path
PEDESTRIAN_OFFSETS = tuple(float(k) for k in range(-4, 5))  # -4 .. +4 m
TIME_SHIFTS = (-4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0)  # s
MIN_VARIANT_SPAN = 2.0  # s

# ---------------------------------------------------------------- validity
MAX_SPEED = 40.0  # m/s, vehicles and motorcycles
MAX_ACCEL = 8.0  # m/s^2, about 0.8 g
BICYCLE_MAX_SPEED = 12.0  # m/s
BICYCLE_MAX_ACCEL = 4.0  # m/s^2
PEDESTRIAN_MAX_SPEED = 3.0  # m/s, a slow run
PEDESTRIAN_MAX_ACCEL = 3.0  # m/s^2
ALLOWED_DT = 0.1  # s, an overlap is excused only within this time of an overlap in the recording
# An actor may not appear after the scene start, or vanish before its end, closer than this to the ego:
# in the 10 mini scenes, recorded vehicles start their labels >= 18 m away (97 % beyond 20 m) and
# pedestrians >= 21 m away; a variant that cuts the start of a path makes the actor pop up in the road.
POP_DISTANCE = 20.0  # m, between box centres
EDGE_TOL = 0.25  # s, an actor starting (ending) within this of the scene start (end) is there all along

# ---------------------------------------------------------------- criticality
RARE_TTC = CLOSE_TTC = 1.5  # s, SSAM default (FHWA-HRT-08-051)
RARE_GAP = CLOSE_GAP = 1.0  # m, catches close following at matched speed, where constant-velocity TTC is infinite
DETECT_TTC = 3.0  # s
REACTION = 1.0  # s
COMFORT_DECEL = 3.4  # m/s^2, AASHTO stopping sight distance (FHWA-HRT-04-091)
MAX_DECEL = 8.0  # m/s^2
DECEL_STEP = 0.2  # m/s^2
DECELS = tuple(round(DECEL_STEP * k, 1) for k in range(1, int(round(MAX_DECEL / DECEL_STEP)) + 1))  # 0.2 .. 8.0
MIN_PRESENCE = 2.0  # s present before the critical moment
STANDING_SPEED = 0.5  # m/s, below this the ego counts as standing when it would brake

BASE = {"reaction_s": REACTION, "detect_ttc_s": DETECT_TTC, "comfort_decel": COMFORT_DECEL,
        "max_decel": MAX_DECEL, "close_ttc_s": CLOSE_TTC, "close_gap_m": CLOSE_GAP, "min_presence_s": MIN_PRESENCE}
SENSITIVITY = {"reaction_s": (0.5, 1.0, 1.5, 2.5), "detect_ttc_s": (2.0, 3.0, 4.0),
               "comfort_decel": (2.5, 3.4, 4.5), "max_decel": (6.0, 7.0, 8.0),
               "close_ttc_s": (1.0, 1.5, 2.0), "close_gap_m": (0.5, 1.0, 1.5), "min_presence_s": (1.0, 2.0, 3.0)}
# (reaction, detection TTC) pairs the braking search runs for: the base and each one-at-a-time change
BRAKE_SETTINGS = sorted({(r, DETECT_TTC) for r in SENSITIVITY["reaction_s"]}
                        | {(REACTION, d) for d in SENSITIVITY["detect_ttc_s"]})
GROUPS = ("far", "close", "mild", "hard", "unavoidable", "late")
VALUABLE = ("close", "hard")


def brake_key(reaction: float, detect: float) -> str:
    return f"r{reaction:.1f}_d{detect:.1f}"


# ---------------------------------------------------------------- actors and variants
def actor_class(track: Track) -> str:
    """vehicle | two_wheel | pedestrian (animals count as pedestrians)."""
    if track.kind == "pedestrian":
        return "pedestrian"
    return "two_wheel" if track.category in ("vehicle.bicycle", "vehicle.motorcycle") else "vehicle"


def limits(track: Track) -> tuple[float, float]:
    """(max speed m/s, max acceleration m/s^2) of a plausible actor of this type."""
    if track.kind == "pedestrian":
        return PEDESTRIAN_MAX_SPEED, PEDESTRIAN_MAX_ACCEL
    if track.category == "vehicle.bicycle":
        return BICYCLE_MAX_SPEED, BICYCLE_MAX_ACCEL
    return MAX_SPEED, MAX_ACCEL


def targets(gt: Scene) -> list[str]:
    """Actors: moving vehicles and pedestrians (not the ego) with data for at least MIN_VARIANT_SPAN seconds."""
    return [
        track.name
        for track in gt.tracks
        if track.kind in ("vehicle", "pedestrian")
        and track.name != "ego"
        and not track.is_stationary
        and track.t[-1] - track.t[0] >= MIN_VARIANT_SPAN
    ]


def grid(track: Track | None = None) -> list[tuple[float, float, float]]:
    """(factor, offset, shift) of every variant of one actor: family A then family B."""
    offsets = PEDESTRIAN_OFFSETS if track is not None and track.kind == "pedestrian" else OFFSETS
    family_a = [(f, d, 0.0) for f, d in itertools.product(SPEED_FACTORS, offsets) if (f, d) != (1.0, 0.0)]
    family_b = [(f, 0.0, s) for s, f in itertools.product(TIME_SHIFTS, SPEED_FACTORS)]
    return family_a + family_b


def method_scene(gt: Scene, method: str) -> Scene:
    """Every object reconstructed by method, the ego as recorded."""
    recon = reconstruct(gt, method)
    tracks = [raw if raw.name == "ego" else track for raw, track in zip(gt.tracks, recon.tracks)]
    return Scene(recon.name, recon.origin, recon.duration, tracks)


def retime(track: Track, factor: float, offset: float, shift: float = 0.0,
           duration: float = float("inf")) -> Track | None:
    if len(track.t) < 2:
        return None
    s = arc_length(track.xy)
    s_new = factor * s + offset
    t_new = track.t + shift
    keep = (s_new >= 0) & (s_new <= s[-1]) & (t_new >= -1e-9) & (t_new <= duration + 1e-9)
    if keep.sum() < 2 or t_new[keep][-1] - t_new[keep][0] < MIN_VARIANT_SPAN:
        return None
    _, xy, yaw = drive_along(track.t[keep], s_new[keep], s, track.xy, track.yaw)
    return with_poses(track, t_new[keep], xy, yaw)


def variant_scene(base: Scene, target: str, factor: float, offset: float, shift: float = 0.0) -> Scene | None:
    tracks = []
    for track in base.tracks:
        if track.name == target:
            track = retime(track, factor, offset, shift, base.duration)
            if track is None:
                return None
        tracks.append(track)
    return Scene(base.name, base.origin, base.duration, tracks)


def variant_id(target: str, factor: float, offset: float, shift: float = 0.0) -> str:
    vid = f"{target}_f{factor:.2f}_d{offset:+05.1f}"
    return vid + f"_t{shift:+.1f}" if shift else vid


# ---------------------------------------------------------------- boxes from replay logs
def _box(track: Track, st: SimTrack, t0: float, t1: float) -> BoxTrack | None:
    mask = (st.t >= t0 - 1e-6) & (st.t <= t1 + 1e-6)
    if mask.sum() == 0:
        return None
    length, width, _ = track.size
    return box_track(st.t[mask], st.xy[mask], st.yaw[mask], length, width, track.bbox_center_x)


def other_boxes(gt: Scene, scene: Scene, sim: dict[str, SimTrack], target: str) -> dict[str, BoxTrack]:
    """Boxes of every object except the target, from a replay log, over each object's annotated span."""
    annotated = {track.name: (track.t[0], track.t[-1]) for track in gt.tracks}
    boxes = {}
    for track in scene.tracks:
        if track.name == target or track.name not in sim:
            continue
        box = _box(track, sim[track.name], *annotated[track.name])
        if box is not None:
            boxes[track.name] = box
    return boxes


def target_box(scene: Scene, sim: dict[str, SimTrack], target: str) -> BoxTrack | None:
    """Box of the target from a replay log, over the target's (variant) span."""
    track = next(tr for tr in scene.tracks if tr.name == target)
    return _box(track, sim[target], track.t[0], track.t[-1]) if target in sim else None


def _reach(box: BoxTrack):
    r = 0.5 * float(np.hypot(box.length, box.width))
    return box.centre.min(axis=0) - r, box.centre.max(axis=0) + r


def _may_touch(a: BoxTrack, b: BoxTrack) -> bool:
    """Cheap pre-check: time spans and swept bounding rectangles intersect."""
    if max(a.t[0], b.t[0]) > min(a.t[-1], b.t[-1]):
        return False
    (amin, amax), (bmin, bmax) = _reach(a), _reach(b)
    return bool((amin <= bmax).all() and (bmin <= amax).all())


def overlap_times(target: BoxTrack, others: dict[str, BoxTrack]) -> dict[str, np.ndarray]:
    """For each object whose box overlaps the target's, the times at which they overlap."""
    out = {}
    for name, box in others.items():
        if _may_touch(target, box):
            m = pair_measures(target, box, with_ttc=False)
            if m["overlap"].any():
                out[name] = m["t"][m["overlap"]]
    return out


def overlapping(target: BoxTrack, others: dict[str, BoxTrack]) -> set[str]:
    """Objects whose box overlaps the target's at some time."""
    return set(overlap_times(target, others))


def _excused(times: np.ndarray, prior: np.ndarray | None) -> np.ndarray:
    if prior is None or not len(prior) or not len(times):
        return np.zeros(len(times), bool)
    return np.abs(times[:, None] - prior[None, :]).min(axis=1) <= ALLOWED_DT


def new_collisions(target: BoxTrack, others: dict[str, BoxTrack], allowed: dict[str, np.ndarray]) -> list[str]:
    """Objects the target overlaps at a time when it did not overlap them in the recording
    (within ALLOWED_DT). Overlaps already present there come from annotation boxes and are ignored."""
    return sorted(name for name, times in overlap_times(target, others).items()
                  if not _excused(times, allowed.get(name)).all())


def points_in_ring(points: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Even-odd ray casting: which points (N, 2) lie inside the closed ring (M, 2)."""
    x, y = points[:, 0:1], points[:, 1:2]
    x0, y0 = ring[:, 0], ring[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    crosses = (y0 > y) != (y1 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    return (crosses & (x < xc)).sum(axis=1) % 2 == 1


def on_road_fraction(box: BoxTrack, polygons, origin) -> float:
    """Share of the box-centre samples inside the drivable area (polygons in the global frame)."""
    points = box.centre + np.asarray(origin, float)
    inside = np.zeros(len(points), bool)
    lo, hi = points.min(axis=0), points.max(axis=0)
    for exterior, holes in polygons:
        if (exterior.max(axis=0) < lo).any() or (exterior.min(axis=0) > hi).any():
            continue
        hit = points_in_ring(points, exterior)
        for hole in holes:
            hit &= ~points_in_ring(points, hole)
        inside |= hit
    return float(inside.mean()) if len(points) else 0.0


# ---------------------------------------------------------------- assessment
def thresholds() -> dict:
    return {"min_variant_span_s": MIN_VARIANT_SPAN, "max_speed_mps": MAX_SPEED, "max_accel_mps2": MAX_ACCEL,
            "bicycle_max_speed_mps": BICYCLE_MAX_SPEED, "bicycle_max_accel_mps2": BICYCLE_MAX_ACCEL,
            "pedestrian_max_speed_mps": PEDESTRIAN_MAX_SPEED, "pedestrian_max_accel_mps2": PEDESTRIAN_MAX_ACCEL,
            "allowed_dt_s": ALLOWED_DT, "pop_distance_m": POP_DISTANCE, "edge_tol_s": EDGE_TOL, "rare_ttc_s": RARE_TTC, "rare_gap_m": RARE_GAP,
            **BASE, "decels_mps2": list(DECELS), "standing_speed_mps": STANDING_SPEED}


def _braking(ego: BoxTrack, actor: BoxTrack, measures: dict, crash_t: float, excused: np.ndarray) -> dict:
    """The reference driver's needed deceleration for each (reaction, detection TTC) setting."""
    out = {}
    speed = np.hypot(*ego.velocity.T)
    path_ttcs = path_ttc(ego, actor, measures["t"])
    for reaction, detect in BRAKE_SETTINGS:
        # Detected when either the constant-velocity TTC or the path TTC (the ego along its own path, the
        # actor straight on) drops below `detect`. On a bend, straight-line extrapolation of both misses
        # the conflict until the boxes are a few metres apart (scene-0061, car_008: TTC infinite down to
        # a 3.4 m gap); a driver knows the road ahead but not the other's intentions.
        cv = measures["t"][measures["ttc"] < detect]  # never empty: TTC is 0 at the crash
        along = measures["t"][path_ttcs < detect]
        t_detect = float(min(cv[0], along[0])) if len(along) else float(cv[0])
        t_brake = t_detect + reaction
        entry = {"t_detect": t_detect, "detected_by": "path" if len(along) and along[0] < cv[0] else "ttc",
                 "t_brake": t_brake, "a_need": None, "monotone": None,
                 "ego_speed": float(np.interp(t_brake, ego.t, speed))}
        if crash_t < t_brake - 1e-9:
            entry["reason"] = "reaction"
        else:
            avoided = braking_avoids(ego, actor, t_brake, np.array(DECELS), excused, ALLOWED_DT)
            if avoided.any():
                k = int(np.argmax(avoided))
                entry.update(a_need=DECELS[k], monotone=bool(avoided[k:].all()), reason=None)
            else:
                entry["reason"] = "standing" if entry["ego_speed"] < STANDING_SPEED else "no_decel"
        out[brake_key(reaction, detect)] = entry
    return out


def pops(target: BoxTrack, ego: BoxTrack | None, duration: float | None) -> list[str]:
    """"pop_in" / "pop_out" when the actor appears after the scene start / vanishes before its end
    closer than POP_DISTANCE to the ego (box centres)."""
    if ego is None or duration is None:
        return []
    out = []
    for reason, t, late in (("pop_in", float(target.t[0]), target.t[0] > EDGE_TOL),
                            ("pop_out", float(target.t[-1]), target.t[-1] < duration - EDGE_TOL)):
        if late and ego.t[0] - 1e-6 <= t <= ego.t[-1] + 1e-6:
            gap = np.hypot(*(np.interp(t, target.t, target.centre[:, k]) - np.interp(t, ego.t, ego.centre[:, k])
                             for k in (0, 1)))
            if gap < POP_DISTANCE:
                out.append(reason)
    return out


def assess(target: BoxTrack | None, others: dict[str, BoxTrack], allowed: dict[str, np.ndarray],
           limit: tuple[float, float] = (MAX_SPEED, MAX_ACCEL), soft: frozenset = frozenset(),
           duration: float | None = None) -> dict:
    """Validity and criticality of the target's replayed box against the other objects.
    allowed: overlap times per object in the recording (see new_collisions); limit: (speed, accel);
    soft: objects a contact with does not invalidate the variant (pedestrians, for a pedestrian actor:
    people walking side by side step around each other); such contacts are listed as "soft_contacts";
    duration: the scene duration, for the pop-in / pop-out check (skipped when None)."""
    if target is None:
        return {"valid": False, "reasons": ["missing_in_log"], "rare": False, "group": None, "valuable": False}
    dyn = dynamics(target)
    touched = new_collisions(target, {k: v for k, v in others.items() if k != "ego"}, allowed)
    hits = [name for name in touched if name not in soft]
    soft_contacts = [name for name in touched if name in soft]
    ego = pair_measures(target, others["ego"]) if "ego" in others else None
    measured = ego is not None and len(ego["t"]) > 0
    row = {
        "min_ttc_ego": float(ego["ttc"].min()) if measured else float("inf"),
        "min_gap_ego": float(ego["gap"].min()) if measured else float("inf"),
        # any real overlap with the ego, also at times when the recording overlaps it
        "ego_collision": bool(measured and ego["overlap"].any()),
        "crash": False, "excused_overlap": False, "conflict": None, "presence_s": None,
    }
    if measured:
        excused = _excused(ego["t"], allowed.get("ego"))
        crashing = ego["overlap"] & ~excused
        row["crash"] = bool(crashing.any())
        row["excused_overlap"] = bool((ego["overlap"] & excused).any())
        if row["crash"]:
            k = int(np.argmax(crashing))
        else:
            k = int(np.lexsort((ego["gap"], ego["ttc"]))[0])  # smallest TTC, then smallest gap
        row["critical_t"] = float(ego["t"][k])
        row["presence_s"] = row["critical_t"] - float(target.t[0])
        row["conflict"] = side_of(target, others["ego"], row["critical_t"])
    reasons = []
    if dyn["max_speed"] > limit[0]:
        reasons.append("speed")
    if dyn["max_accel"] > limit[1]:
        reasons.append("accel")
    if hits:
        reasons.append("collision")
    reasons += pops(target, others.get("ego"), duration)
    valid = not reasons
    if valid and row["crash"]:
        row["braking"] = _braking(others["ego"], target, ego, row["critical_t"],
                                  ego["t"][ego["overlap"] & excused])
    out = {"valid": valid, "reasons": reasons, "span_s": float(target.t[-1] - target.t[0]), **dyn,
           "collisions": hits, "soft_contacts": soft_contacts, **row, "rare": valid and critical(row)}
    out["group"] = classify(out)
    out["valuable"] = out["group"] in VALUABLE
    return out


def critical(row: dict, close_ttc: float = CLOSE_TTC, close_gap: float = CLOSE_GAP) -> bool:
    """TTC or gap below the close thresholds (version 1 "rare", without the validity check)."""
    return row.get("min_ttc_ego", float("inf")) < close_ttc or row.get("min_gap_ego", float("inf")) < close_gap


def classify(row: dict, th: dict | None = None) -> str | None:
    """Group of a valid assessed row under thresholds th (default BASE); None when not valid."""
    th = {**BASE, **(th or {})}
    if not row.get("valid"):
        return None
    late = row.get("presence_s") is not None and row["presence_s"] < th["min_presence_s"] - 1e-9
    if row.get("crash"):
        if late:
            return "late"
        entry = row["braking"][brake_key(th["reaction_s"], th["detect_ttc_s"])]
        a = entry["a_need"]
        if a is None or a > th["max_decel"] + 1e-9:
            return "unavoidable"
        return "mild" if a <= th["comfort_decel"] + 1e-9 else "hard"
    if critical(row, th["close_ttc_s"], th["close_gap_m"]):
        return "late" if late else "close"
    return "far"


def unavoidable_reason(row: dict, th: dict | None = None) -> str:
    th = {**BASE, **(th or {})}
    entry = row["braking"][brake_key(th["reaction_s"], th["detect_ttc_s"])]
    return entry["reason"] or "too_hard"


# ---------------------------------------------------------------- summaries
def events(rows) -> set[tuple[str, str]]:
    """Distinct (actor, conflict type) pairs; conflict type = actor type / side of the ego."""
    return {(row["target"], f"{row['actor']}/{row['conflict']}") for row in rows}


def _group_events(rows, th=None) -> dict[str, set]:
    by = {g: [] for g in GROUPS}
    for row in rows:
        group = classify(row, th)
        if group is not None:
            by[group].append(row)
    return {g: events(r) for g, r in by.items()}, {g: len(r) for g, r in by.items()}


def summarize(rows: list[dict], original: dict[str, dict], recorded: dict[str, dict]) -> dict:
    """Counts over the variants of one method. original: each target's unmodified reconstruction;
    recorded: each target in the recording (the same for every method). Rows carry "target" and "actor"."""
    reasons = {}
    for row in rows:
        for reason in row["reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1
    valid = [row for row in rows if row["valid"]]
    written = [row for row in rows if "span" not in row["reasons"]]
    rare = [row for row in rows if row["rare"]]
    # the recording is what happened: its events count whatever its (label-noise) dynamics look like
    rec_rows = [{**row, "valid": True} for row in recorded.values() if "conflict" in row]
    recorded_events = events(row for row in rec_rows if critical(row))

    group_events, group_files = _group_events(valid)
    rec_group_events, _ = _group_events(rec_rows)
    valuable = set().union(*(group_events[g] for g in VALUABLE))
    rec_valuable = set().union(*(rec_group_events[g] for g in VALUABLE))
    unavoidable = {}
    for row in valid:
        if classify(row) == "unavoidable":
            reason = unavoidable_reason(row)
            unavoidable[reason] = unavoidable.get(reason, 0) + 1
    by_type = {}
    for _, conflict in valuable - rec_valuable:
        by_type[conflict] = by_type.get(conflict, 0) + 1

    sensitivity = []
    for name, values in SENSITIVITY.items():
        for value in values:
            th = {name: value}
            ev, _ = _group_events(valid, th)
            rev, _ = _group_events(rec_rows, th)
            new = set().union(*(ev[g] for g in VALUABLE)) - set().union(*(rev[g] for g in VALUABLE))
            sensitivity.append({"threshold": name, "value": value, "base": value == BASE[name],
                                "new_valuable_events": len(new)})

    crash_rows = [row for row in valid if row["crash"]]
    return {
        "targets": len(original),
        "generated": len(rows),
        "written": len(written),
        "valid": len(valid),
        "valid_rate": len(valid) / len(written) if written else 0.0,
        "rejected_by": dict(sorted(reasons.items())),
        "rejected_geometry": sum(any(r in ("collision", "missing_in_log", "pop_in", "pop_out") for r in row["reasons"])
                                 for row in written),
        "rejected_dynamics": sum(any(r in ("speed", "accel") for r in row["reasons"]) for row in written),
        # version 2
        "outcome": {"crash": len(crash_rows), "close": sum(not row["crash"] and critical(row) for row in valid),
                    "far": sum(not row["crash"] and not critical(row) for row in valid)},
        "groups": group_files,
        "group_events": {g: len(e) for g, e in group_events.items()},
        "valuable": sum(group_files[g] for g in VALUABLE),
        "valuable_events": len(valuable),
        "new_valuable_events": len(valuable - rec_valuable),
        "recorded_valuable_events": len(rec_valuable),
        "new_valuable_by_type": dict(sorted(by_type.items())),
        "unavoidable_reasons": dict(sorted(unavoidable.items())),
        "excused_overlap_only": sum(row["excused_overlap"] and not row["crash"] for row in valid),
        "valid_with_pedestrian_contact": sum(bool(row.get("soft_contacts")) for row in valid),
        "valid_by_actor": {a: sum(row["actor"] == a for row in valid) for a in ("vehicle", "two_wheel", "pedestrian")},
        "written_by_actor": {a: sum(row["actor"] == a for row in written) for a in ("vehicle", "two_wheel", "pedestrian")},
        "non_monotone": sum(row["braking"][brake_key(REACTION, DETECT_TTC)]["monotone"] is False for row in crash_rows),
        "sensitivity": sensitivity,
        # version 1, for comparison
        "rare": len(rare),
        "rare_near_miss": sum(not row["ego_collision"] for row in rare),
        "rare_targets": len({row["target"] for row in rare}),
        "rare_events": len(events(rare)),
        "new_rare_events": len(events(rare) - recorded_events),
        "recorded_rare_events": len(recorded_events),
        "valid_ego_collision": sum(row["ego_collision"] for row in valid),
        "kept_xosc": sum(row.get("kept", False) for row in rows),
        "full_replay_failed": reasons.get("full_replay", 0),
        "original_on_road_min": min((row["on_road_fraction"] for row in original.values() if "on_road_fraction" in row),
                                    default=None),
        "original_valid": sum(row["valid"] for row in original.values()),
    }


def format_summary(summary: dict) -> str:
    """Plain ASCII: the command line may print to a console that cannot show Vietnamese."""
    groups = ", ".join(f"{g} {summary['groups'][g]} ({summary['group_events'][g]} ev)" for g in GROUPS)
    lines = [
        f"targets {summary['targets']}, parameter combinations {summary['generated']}, "
        f"scenarios written {summary['written']} (others keep < {MIN_VARIANT_SPAN:g} s)",
        f"valid {summary['valid']} ({100 * summary['valid_rate']:.1f}% of written); rejected: geometry "
        f"{summary['rejected_geometry']}, dynamics {summary['rejected_dynamics']} {summary['rejected_by']}",
        f"valid / written by actor: " + ", ".join(f"{a} {summary['valid_by_actor'][a]}/{summary['written_by_actor'][a]}"
                                                   for a in summary["valid_by_actor"])
        + f"; valid with a pedestrian-pedestrian contact {summary['valid_with_pedestrian_contact']}",
        f"if the ego does not react: {summary['outcome']}",
        f"groups (files, events): {groups}",
        f"VALUABLE (close + hard): {summary['valuable']} files, {summary['valuable_events']} events, "
        f"{summary['new_valuable_events']} not in the recording ({summary['recorded_valuable_events']} there); "
        f"by type {summary['new_valuable_by_type']}",
        f"unavoidable by braking: {summary['unavoidable_reasons']}; non-monotone braking {summary['non_monotone']}",
        f"version 1 (TTC < {RARE_TTC} s or gap < {RARE_GAP} m): rare {summary['rare']} files, "
        f"{summary['rare_events']} events, {summary['new_rare_events']} not in the recording",
        f"full-scene .xosc kept {summary['kept_xosc']} (full replay failed: {summary['full_replay_failed']}); "
        f"unmodified reconstruction: {summary['original_valid']}/{summary['targets']} targets valid",
    ]
    if summary.get("original_on_road_min") is not None:
        lines.append(f"targets inside the map's drivable area: at least {100 * summary['original_on_road_min']:.1f}% "
                     "of each target's samples")
    return "\n".join(lines)


def format_comparison(summaries: dict[str, dict]) -> str:
    keys = ("generated", "written", "valid", "valid_rate", "valuable", "valuable_events", "new_valuable_events",
            "recorded_valuable_events", "rare", "rare_events")
    lines = [f"{'':<26}" + "".join(f"{m:>12}" for m in summaries)]
    for key in keys:
        cells = "".join(
            f"{s[key]:>12.3f}" if isinstance(s[key], float) else f"{s[key]:>12}" for s in summaries.values()
        )
        lines.append(f"{key:<26}{cells}")
    return "\n".join(lines)
