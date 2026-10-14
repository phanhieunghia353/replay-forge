"""Stage 1 events: candidates, validity and rare-case grouping (docs/thiet-ke-kich-ban-hanh-vi.md, 4.3-4.8).

One validator for both methods of metric 2:
  baseline  the event vehicle brakes, nobody reacts (behavior.simulate(react=False))
  pilot     the vehicles behind it react like human drivers (react=True)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from real2sim import behavior
from real2sim.behavior import DT, Event, Outcome, SceneModel, centres, find_leader, simulate
from real2sim.safety import box_track, braking_avoids, corners, pair_measures, resample
from real2sim.tracks import Scene, Track

# ---------------------------------------------------------------- grid (fixed before any run)
EVENT_STEP = 2.0  # s between event start times
EVENT_SPEED = 3.0  # m/s, the event vehicle must move at least this fast at t0
DECELS = (2.0, 4.0, 6.0, 8.0)  # m/s^2
TARGETS = (("stop", 0.0), ("stop", 3.0), ("half", 0.0))  # (target, dwell s)
AFTER_EVENT = 4.0  # s of scene left after the event ends
FOLLOW_WINDOW = (-0.5, 3.0)  # s around t0 in which someone must be following the event vehicle
ACTOR_DATA_AFTER = 4.0  # s of recorded data the event vehicle must still have after t0

# ---------------------------------------------------------------- validity
MAX_ACCEL = 4.0  # m/s^2, simulated acceleration
DECEL_SLACK = 0.2  # m/s^2, allowed over a vehicle's emergency braking limit (behavior.MAX_DECEL, HEAVY_MAX_DECEL)
LABEL_REACH = 5.0  # m, a physics violation this close (along the path) to one in the vehicle's own recorded
#                   motion is a label error of the data, not something the variant did
SPEED_LIMIT = 40.0  # m/s
PHYSICS_SMOOTH = 4  # grid steps (0.2 s) of speed averaging before differentiating
EDGE_SKIP = 0.2  # s at both ends of a trajectory left out when measuring the esmini replay's dynamics
TAILGATE_GAP = 0.5  # m, bumper gap ...
TAILGATE_SPEED = 3.0  # m/s, ... while moving faster than this ...
TAILGATE_TIME = 0.5  # s, ... for longer than this
EXEMPT_ALONG = 1.5  # m, an overlap is excused when the recording has one of the same pair this close along ...
EXEMPT_ACROSS = 0.75  # m, ... and across (relative position of the two boxes; a turning bus beside a car
#                       shifts this by ~0.5 m when timing changes; a rear-end has |across| ~ 0, far from
#                       side-by-side label overlaps) ...
EXEMPT_DEPTH = 0.1  # m, ... and when not deeper than there by more than this
APPEAR_WINDOW = 2.0  # s, a collision this soon after one of the pair entered the data is an appearing problem
MERGE_LOOKBACK = 3.0  # s, a pair whose headings differed by more than HEADING_TOL in this time before contact
#                      was merging or crossing, not following (stage 1 does not simulate merges)

# ---------------------------------------------------------------- rare cases (criteria v2 thresholds)
CLOSE_GAP = 1.0  # m, only counts for a vehicle on the ego's path (in front or behind), see _on_path
CLOSE_TTC = 1.5  # s, counts on any side
COMFORT_DECEL = 3.4  # m/s^2
NEW_MARGIN = 0.1  # m or s: closer than the same pair in the recording by at least this to count as new
DECEL_GRID = np.round(np.arange(0.2, 8.0 + 1e-9, 0.2), 1)
GROUPS = ("collision", "hard", "close", "mild", "far")
VALUABLE = ("hard", "close")


# ---------------------------------------------------------------- candidates
def can_start(model: SceneModel, e: int, t0: float) -> bool:
    """Whether vehicle e can start braking at t0: it moves fast enough, its recorded data outlasts t0 by
    ACTOR_DATA_AFTER, and some vehicle follows it for FOLLOW_MIN_TIME within FOLLOW_WINDOW around t0."""
    a = model.agents[e]
    if a.is_ego or not model.movers[e]:
        return False
    k0 = int(round(t0 / DT))
    if k0 >= model.K or np.isnan(model.V[k0, e]) or model.V[k0, e] < EVENT_SPEED:
        return False
    if model.t[a.k1] < t0 + ACTOR_DATA_AFTER:  # its recorded data must outlast the event start
        return False
    lo = max(0, k0 + int(FOLLOW_WINDOW[0] / DT))
    hi = min(model.K, k0 + int(FOLLOW_WINDOW[1] / DT) + 1)
    hold = int(round(behavior.FOLLOW_MIN_TIME / DT))
    return bool((model.leader[lo:hi] == e).sum(axis=0).max() >= hold)


def fits(model: SceneModel, event: Event) -> bool:
    """Whether the event (braking, dwell, getting back to speed) ends AFTER_EVENT before the scene does."""
    e = model.index[event.actor]
    v0 = model.V[int(round(event.t0 / DT)), e]
    ends = event.t0 + (v0 if event.target == "stop" else v0 / 2) / event.decel + event.dwell + v0 / behavior.IDM_A
    return bool(ends + AFTER_EVENT <= model.duration)


def candidates(model: SceneModel) -> list[Event]:
    """Every event of the fixed grid that the scene supports (a moving vehicle someone follows, enough time)."""
    out = []
    for e in np.flatnonzero(model.movers):
        a = model.agents[e]
        for t0 in np.arange(EVENT_STEP / 2, model.duration, EVENT_STEP):
            if not can_start(model, e, float(t0)):
                continue
            for decel in DECELS:
                if decel > a.max_decel + 1e-9:  # a bus or truck cannot brake this hard
                    continue
                for target, dwell in TARGETS:
                    event = Event(a.name, round(float(t0), 2), decel, target, dwell)
                    if fits(model, event):
                        out.append(event)
    return out


def selectable(model: SceneModel, step: float = 0.5) -> dict:
    """Vehicles a user may make brake, with the start times (every `step` s) at which they can, and the
    hardest braking they are capable of."""
    out = {}
    for e in np.flatnonzero(model.movers):
        a = model.agents[e]
        times = [round(float(t), 2) for t in np.arange(0.0, model.duration, step) if can_start(model, e, float(t))]
        if times:
            out[a.name] = {"times": times, "max_decel": a.max_decel}
    return out


def label_problems(model: SceneModel) -> dict:
    """Moving vehicles whose own recorded (nominal) motion breaks the physics limits: name -> list of
    [start, end] times (s), steps less than 0.5 s apart merged."""
    out = {}
    for i in np.flatnonzero(model.movers):
        bad = _physics_violations(model.X, model.Y, i, model.agents[i].max_decel)
        if not len(bad):
            continue
        spans, start, prev = [], bad[0], bad[0]
        for k in bad[1:]:
            if (k - prev) * DT > 0.5:
                spans.append([round(float(model.t[start]), 2), round(float(model.t[prev]), 2)])
                start = k
            prev = k
        spans.append([round(float(model.t[start]), 2), round(float(model.t[prev]), 2)])
        out[model.agents[i].name] = spans
    return out


def encounter_id(event: Event) -> str:
    return f"{event.actor}@{event.t0:.0f}s_{event.target}"


def variant_id(event: Event) -> str:
    dwell = f"_d{event.dwell:.0f}" if event.target == "stop" else ""
    return f"{event.actor}_t{event.t0:04.1f}_{event.target}{dwell}_a{event.decel:.0f}"


# ---------------------------------------------------------------- geometry helpers
def _box(model, X, Y, H, k, i):
    a = model.agents[i]
    return corners(np.array([X[k, i], Y[k, i]]), np.array(H[k, i]), a.length, a.width)


def penetration(a: np.ndarray, b: np.ndarray) -> float:
    """Overlap depth of two rectangles (4, 2): smallest overlap of their projections on the 4 edge axes (0 if apart)."""
    axes = []
    for box in (a, b):
        for e in (box[1] - box[0], box[3] - box[0]):
            axes.append(e / np.linalg.norm(e))
    depth = np.inf
    for ax in axes:
        pa, pb = a @ ax, b @ ax
        d = min(pa.max(), pb.max()) - max(pa.min(), pb.min())
        if d <= 0:
            return 0.0
        depth = min(depth, d)
    return float(depth)


def _midpoints(X, Y, H):
    """Positions halfway between grid steps (checks every DT/2 = 0.025 s)."""
    return (X[:-1] + X[1:]) / 2, (Y[:-1] + Y[1:]) / 2, H[:-1] + behavior._wrap(H[1:] - H[:-1]) / 2


# ---------------------------------------------------------------- assessment
@dataclass
class Assessment:
    valid: bool
    reasons: list
    collisions: list  # (agent, other, time, kind) kind = following | crossing | ego
    group: str | None
    ego: dict
    reacted: list
    max_decel_used: dict
    details: dict | None = None  # measured values behind each check (for the app's technical view)


def assess(model: SceneModel, outcome: Outcome) -> Assessment:
    X, Y, H = centres(model, outcome)
    ego = model.index["ego"]
    changed = np.flatnonzero(outcome.changed)
    reasons, collisions = [], []

    # 1. physics of every agent whose motion changed; where its own recorded motion breaks the same limits
    #    at the same place, the data has a label error (still invalid: the scenario would show it)
    physics = {}
    for i in changed:
        physics[model.agents[i].name] = _dynamics_extremes(model, X, Y, i)
        bad = _physics_violations(X, Y, i, model.agents[i].max_decel)
        if not len(bad):
            continue
        recorded = _physics_violations(model.X, model.Y, i, model.agents[i].max_decel)
        s_bad, s_rec = outcome.S[bad, i], model.S[recorded, i]
        label = len(s_rec) > 0 and all(np.abs(s_rec - s).min() <= LABEL_REACH for s in s_bad)
        reasons.append("label_error" if label else "physics")

    # 2. overlaps of changed agents with anyone, against the recording, at every DT/2
    seen = set()
    excused = []
    Xm, Ym, Hm = _midpoints(X, Y, H)
    frames = [(X, Y, H, 0.0), (Xm, Ym, Hm, DT / 2)]
    diag = np.array([math.hypot(a.length, a.width) / 2 for a in model.agents])
    for i in changed:
        for j in range(len(model.agents)):
            if j == i or (j in changed and j < i) or (i, j) in seen:
                continue
            for Xf, Yf, Hf, shift in frames:
                d = np.hypot(Xf[:, i] - Xf[:, j], Yf[:, i] - Yf[:, j])
                close = np.flatnonzero(d < diag[i] + diag[j])
                hit = None
                for k in close:
                    bi, bj = _box(model, Xf, Yf, Hf, k, i), _box(model, Xf, Yf, Hf, k, j)
                    depth = penetration(bi, bj)
                    if depth <= 0:
                        continue
                    if _excused(model, Xf, Yf, Hf, k, i, j, depth):
                        if len(excused) < 20 and (i, j) not in {(e[3], e[4]) for e in excused}:
                            excused.append((model.agents[i].name, model.agents[j].name,
                                            round(float(model.t[k] + shift), 2), i, j))
                        continue
                    hit = (k, shift)
                    break
                if hit is not None:
                    k, shift = hit
                    t = model.t[k] + shift
                    other = j if i == ego else i
                    appeared = max(model.t[model.agents[i].k0], model.t[model.agents[j].k0])
                    if t - appeared < APPEAR_WINDOW and appeared > 0:
                        # one of them only just entered the recorded data, where the changed situation now is:
                        # where it would have been before is unknown (stage 2: rules for appearing)
                        kind = "appearing"
                    elif ego in (i, j) and outcome.changed[other] and model.vehicles[other]:
                        kind = "ego"  # the ego meets the event chain
                    elif ego in (i, j) or not (model.vehicles[i] and model.vehicles[j]):
                        # the ego (now delayed) or a vehicle meets someone replaying who would react in reality
                        # (pedestrians, objects, crossing traffic): not simulated in stage 1
                        kind = "crossing"  # pedestrians, objects: not simulated in stage 1
                    else:
                        kind = "crossing" if _merging(Hf, k, i, j) else "following"
                    collisions.append((model.agents[i].name, model.agents[j].name, round(float(t), 3), kind))
                    seen.add((i, j))
                    seen.add((j, i))
                    break
    kinds = {c[3] for c in collisions}
    if "crossing" in kinds:
        reasons.append("unsupported_interaction")
    if "appearing" in kinds:
        reasons.append("unsupported_appearing")
    if "following" in kinds:
        reasons.append("collision")

    # 3. tailgating behind a changed vehicle (or by one), not present in the recording
    if _tailgating(model, outcome, X, Y, H, changed):
        reasons.append("tailgating")

    ego_info = _ego(model, outcome, X, Y, H, changed, collisions)
    reasons = sorted(set(reasons))
    valid = not reasons
    group = ego_info["group"] if valid else None
    reacted = sorted(outcome.driving_from)
    used = {model.agents[i].name: round(float(-np.nanmin(np.minimum(outcome.A[:, i], 0))), 2) for i in changed}
    details = {"physics": physics, "excused": [e[:3] for e in excused], "gaps": _closest_gaps(model, outcome)}
    return Assessment(valid, reasons, collisions, group, ego_info, reacted, used, details)


def _physics_violations(X, Y, i, max_decel) -> np.ndarray:
    """Grid steps where agent i's motion, measured from its positions (a path end or any jump shows up) and
    averaged over PHYSICS_SMOOTH steps, is faster than SPEED_LIMIT, accelerates harder than MAX_ACCEL or
    brakes harder than its limit plus DECEL_SLACK."""
    idx = np.flatnonzero(~np.isnan(X[:, i]))
    if len(idx) < 2 * PHYSICS_SMOOTH:
        return idx[:0]
    step = np.hypot(np.diff(X[idx, i]), np.diff(Y[idx, i]))
    v = np.convolve(np.concatenate([[step[0]], step]) / DT, np.ones(PHYSICS_SMOOTH) / PHYSICS_SMOOTH, mode="valid")
    acc = np.gradient(v, DT)
    bad = (v > SPEED_LIMIT) | (acc > MAX_ACCEL) | (acc < -(max_decel + DECEL_SLACK))
    return idx[np.flatnonzero(bad) + PHYSICS_SMOOTH // 2]


def _dynamics_extremes(model, X, Y, i) -> dict:
    """Fastest speed, hardest acceleration and braking of agent i (measured as the physics check does), with
    the time of each, and the limits that apply to it."""
    idx = np.flatnonzero(~np.isnan(X[:, i]))
    out = {"max_speed": None, "max_accel": None, "t_accel": None, "max_decel": None, "t_decel": None,
           "limit_accel": MAX_ACCEL, "limit_decel": model.agents[i].max_decel + DECEL_SLACK}
    if len(idx) < 2 * PHYSICS_SMOOTH:
        return out
    step = np.hypot(np.diff(X[idx, i]), np.diff(Y[idx, i]))
    v = np.convolve(np.concatenate([[step[0]], step]) / DT, np.ones(PHYSICS_SMOOTH) / PHYSICS_SMOOTH, mode="valid")
    acc = np.gradient(v, DT)
    at = model.t[idx[np.arange(len(acc)) + PHYSICS_SMOOTH // 2]]
    out.update(max_speed=round(float(v.max()), 2), max_accel=round(float(acc.max()), 2),
               t_accel=round(float(at[np.argmax(acc)]), 2), max_decel=round(float(-acc.min()), 2),
               t_decel=round(float(at[np.argmin(acc)]), 2))
    return out


def _closest_gaps(model, outcome) -> dict:
    """Smallest bumper gap each driving agent kept to the vehicle ahead of it, with its time and speed then."""
    out = {}
    if outcome.gap is None:
        return out
    for i in np.flatnonzero(outcome.changed):
        g = outcome.gap[:, i]
        if np.all(np.isnan(g)):
            continue
        k = int(np.nanargmin(g))
        out[model.agents[i].name] = {"gap": round(float(g[k]), 3), "t": round(float(model.t[k]), 2),
                                     "speed": round(float(outcome.V[k, i]), 2),
                                     "leader": model.agents[outcome.leader[k, i]].name}
    return out


def _merging(H, k, i, j) -> bool:
    """Whether i and j were not travelling along the same direction (within HEADING_TOL, either way) at some
    time in the MERGE_LOOKBACK before step k."""
    lo = max(0, k - int(round(MERGE_LOOKBACK / DT)))
    dh = np.abs(behavior._wrap(H[lo:k + 1, i] - H[lo:k + 1, j]))
    dh = np.minimum(dh, math.pi - dh)
    return bool(np.nanmax(dh, initial=0.0) > behavior.HEADING_TOL)


def _relative(X, Y, H, k, i, j):
    """Position of i's centre in j's frame (along, across)."""
    h = H[k, j]
    dx, dy = X[k, i] - X[k, j], Y[k, i] - Y[k, j]
    return dx * math.cos(h) + dy * math.sin(h), -dx * math.sin(h) + dy * math.cos(h)


def _recorded_overlaps(model, i, j) -> list:
    """(along, across, depth) of every recorded overlap of the pair (i, j), cached on the model."""
    cache = model.__dict__.setdefault("_overlap_cache", {})
    key = (min(i, j), max(i, j))
    if key not in cache:
        found = []
        both = ~np.isnan(model.X[:, i]) & ~np.isnan(model.X[:, j])
        near = both & (np.hypot(model.X[:, i] - model.X[:, j], model.Y[:, i] - model.Y[:, j])
                       < (math.hypot(model.agents[i].length, model.agents[i].width)
                          + math.hypot(model.agents[j].length, model.agents[j].width)) / 2)
        for k in np.flatnonzero(near):
            d = penetration(_box(model, model.X, model.Y, model.H, k, key[0]),
                            _box(model, model.X, model.Y, model.H, k, key[1]))
            if d > 0:
                found.append((*_relative(model.X, model.Y, model.H, k, key[0], key[1]), d))
        cache[key] = found
    return cache[key]


def _excused(model, X, Y, H, k, i, j, depth) -> bool:
    """The recording has an overlap of the same pair in the same relative position (annotation boxes,
    e.g. passing side by side), not much less deep. Matched by geometry, not by time, so a delayed
    vehicle repeating the same side-by-side moment is still excused; a rear-end collision is not."""
    lo, hi = min(i, j), max(i, j)
    along, across = _relative(X, Y, H, k, lo, hi)
    for r_along, r_across, r_depth in _recorded_overlaps(model, i, j):
        if abs(along - r_along) < EXEMPT_ALONG and abs(across - r_across) < EXEMPT_ACROSS \
                and depth <= r_depth + EXEMPT_DEPTH:
            return True
    return False


def _tailgating(model, outcome, X, Y, H, changed) -> bool:
    need = int(round(TAILGATE_TIME / DT))
    run = {}
    pres = ~np.isnan(X)
    for k in range(model.K):
        if not len(changed):
            break
        live = changed[pres[k, changed]]
        if not len(live):
            run.clear()
            continue
        # only vehicles near a changed one can have it as leader (or be a changed one)
        d = np.hypot(X[k][:, None] - X[k, live][None, :], Y[k][:, None] - Y[k, live][None, :])
        near = np.nanmin(np.where(np.isnan(d), np.inf, d), axis=1) < behavior.LOOKAHEAD + 20.0
        for i in np.flatnonzero(model.movers & pres[k] & near):
            v = outcome.V[k, i]
            if np.isnan(v) or v <= TAILGATE_SPEED or model.agents[i].is_ego:
                run.pop(i, None)
                continue
            s_i = outcome.S[k, i]
            j, g = find_leader(model, i, s_i, X[k], Y[k], H[k], outcome.V[k], pres[k])
            if j < 0 or model.agents[j].is_ego or not (outcome.changed[i] or outcome.changed[j]):
                run.pop(i, None)
                continue
            recorded = model.gap[k, i]
            if g < TAILGATE_GAP and not (model.leader[k, i] == j and recorded < TAILGATE_GAP + 0.1):
                run[i] = run.get(i, 0) + 1
                if run[i] > need:
                    return True
            else:
                run.pop(i, None)
    return False


def _ego(model, outcome, X, Y, H, changed, collisions) -> dict:
    """What the event means for the ego (criteria v2 thresholds, on the reacting reference driver)."""
    e = model.index["ego"]
    info = {"stimulus": None, "a_min": None, "a_used": None, "min_gap": None, "min_ttc": None, "conflict_with": None,
            "conflict_side": None, "close_by": None}
    ego_hits = [c for c in collisions if c[3] == "ego"]
    others = [i for i in changed if i != e]
    if not others:
        info["group"] = "far"
        return info
    # boxes of the ego as it moved and of every changed agent
    ego_t, ego_box = _track_box(model, X, Y, H, e)
    best, new_close = None, False
    rec_ego = _recorded_ego_box(model)
    for j in others:
        tj, bj = _track_box(model, X, Y, H, j)
        if bj is None or ego_box is None:
            continue
        m = pair_measures(bj, ego_box)
        if not len(m["t"]):
            continue
        on_path = _on_path(bj, ego_box, m["t"])
        gmin, tmin = float(m["gap"].min()), float(m["ttc"].min())
        gpath = float(m["gap"][on_path].min()) if on_path.any() else np.inf
        # the same pair in the recording: closeness that was already there is not new
        _, rj = _track_box(model, model.X, model.Y, model.H, j)
        rec = pair_measures(rj, rec_ego) if rj is not None and rec_ego is not None else None
        rec_ok = rec is not None and len(rec["t"])
        rec_path = _on_path(rj, rec_ego, rec["t"]) if rec_ok else None
        rec_g = float(rec["gap"][rec_path].min()) if rec_ok and rec_path.any() else np.inf
        rec_t = float(rec["ttc"].min()) if rec_ok else np.inf
        by_gap = gpath < CLOSE_GAP and gpath < rec_g - NEW_MARGIN
        by_ttc = tmin < CLOSE_TTC and tmin < rec_t - NEW_MARGIN
        if by_gap or by_ttc:
            new_close = True
        # the most critical partner: a near miss first, then the smaller gap on the ego's path, then TTC
        key = (not (by_gap or by_ttc), gpath, tmin)
        if best is None or key < best[0]:
            if by_gap or not by_ttc:  # the closest moment (on the path when there is one)
                k = int(np.argmin(np.where(on_path, m["gap"], np.inf))) if on_path.any() else int(np.argmin(m["gap"]))
            else:
                k = int(np.argmin(m["ttc"]))
            side = _side(bj, ego_box, float(m["t"][k]), by_bearing=by_ttc and not by_gap)
            best = (key, j, gmin, tmin, rec_g, rec_t, gpath, side, "gap" if by_gap else "ttc" if by_ttc else None)
    if best is not None:
        _, j, gmin, tmin, rec_g, rec_t, gpath, side, close_by = best
        info["conflict_with"] = model.agents[j].name
        info["conflict_side"], info["close_by"] = side, close_by
        info["min_gap"], info["min_ttc"] = round(gmin, 3), round(tmin, 3)
        info["min_gap_path"] = None if np.isinf(gpath) else round(gpath, 3)
        info["recorded_min_gap"] = None if np.isinf(rec_g) else round(rec_g, 3)
        info["recorded_min_ttc"] = None if np.isinf(rec_t) else round(rec_t, 3)
    # when would the reference driver have noticed (same rule as behavior.simulate, on these positions)
    pres = ~np.isnan(X)
    for k in range(model.K):
        if not pres[k, e]:
            continue
        j, _ = find_leader(model, e, outcome.S[k, e], X[k], Y[k], H[k], outcome.V[k], pres[k])
        if j >= 0 and outcome.changed[j] and (outcome.V[k, j] < model.V[k, j] - behavior.DEV_SPEED
                                               or model.S[k, j] - outcome.S[k, j] > behavior.DEV_LAG):
            info["stimulus"] = round(float(model.t[k]), 3)
            break
    if outcome.changed[e]:
        info["a_used"] = round(float(-min(0.0, np.nanmin(outcome.A[:, e]))), 2)
    # smallest braking that avoids every changed agent, braking along the recorded ego path from
    # stimulus + reaction time (as in criteria v2)
    if info["stimulus"] is not None:
        t_brake = info["stimulus"] + outcome.reaction
        rec = _recorded_ego_box(model)
        needed = 0.0
        for j in others:
            tj, bj = _track_box(model, X, Y, H, j)
            if bj is None:
                continue
            ok = braking_avoids(rec, bj, t_brake, DECEL_GRID)
            avoided_without = braking_avoids(rec, bj, t_brake, np.array([0.0]))[0]
            if avoided_without:
                continue
            needed = max(needed, float(DECEL_GRID[np.argmax(ok)]) if ok.any() else np.inf)
        info["a_min"] = None if np.isinf(needed) else round(needed, 1)
        info["a_min_exceeds_grid"] = bool(np.isinf(needed))
    # group, in order of precedence
    if ego_hits:
        group = "collision"
    elif info.get("a_min_exceeds_grid") or (info["a_min"] is not None and info["a_min"] > COMFORT_DECEL):
        group = "hard"
    elif new_close:
        group = "close"
    elif info["stimulus"] is not None and (info["a_min"] or 0) > 0:
        group = "mild"
    else:
        group = "far"
    info["group"] = group
    return info


def _angles(other, ego, t) -> np.ndarray:
    """Bearing (deg, -180..180) of the other box's centre seen from the ego's heading, at times t."""
    ro, re = resample(other, t), resample(ego, t)
    d = ro.centre - re.centre
    c, s = np.cos(re.heading), np.sin(re.heading)
    return np.degrees(np.arctan2(-s * d[:, 0] + c * d[:, 1], c * d[:, 0] + s * d[:, 1]))


def _on_path(other, ego, t) -> np.ndarray:
    """Whether the other box is on the ego's path: across the ego's heading, the two boxes overlap (the other is
    in front of or behind it, in its lane). A vehicle beside it in the next lane, however close, is not."""
    ro, re = resample(other, t), resample(ego, t)
    pts = corners(ro.centre, ro.heading, other.length, other.width)  # (N, 4, 2)
    d = pts - re.centre[:, None, :]
    lateral = -np.sin(re.heading)[:, None] * d[..., 0] + np.cos(re.heading)[:, None] * d[..., 1]
    half = ego.width / 2
    return (lateral.max(axis=1) > -half) & (lateral.min(axis=1) < half)


def _side(other, ego, t: float, by_bearing: bool = False) -> str:
    """front / rear when the other is on the ego's path (_on_path), else left / right. by_bearing: also front /
    rear within 45 degrees of the ego's heading (a vehicle ahead on a bend, met through TTC)."""
    a = float(_angles(other, ego, np.array([t]))[0])
    if _on_path(other, ego, np.array([t]))[0] or (by_bearing and (abs(a) <= 45.0 or abs(a) >= 135.0)):
        return "front" if abs(a) < 90.0 else "rear"
    return "left" if a > 0 else "right"


def _track_box(model, X, Y, H, i):
    ok = ~np.isnan(X[:, i])
    if ok.sum() < 2:
        return None, None
    a = model.agents[i]
    t = model.t[ok]
    # BoxTrack wants reference points; the centres are given, so use centre offset 0
    return t, box_track(t, np.column_stack([X[ok, i], Y[ok, i]]), H[ok, i], a.length, a.width, 0.0)


def _recorded_ego_box(model):
    e = model.index["ego"]
    return _track_box(model, model.X, model.Y, model.H, e)[1]


# ---------------------------------------------------------------- scenario export
def outcome_scene(model: SceneModel, gt: Scene, outcome: Outcome) -> Scene:
    """The scene as one variant plays it: changed agents on their simulated motion (a vertex every DT),
    everyone else as in the pilot reconstruction (the ego: its recording)."""
    from real2sim.variants import method_scene

    base = {tr.name: tr for tr in method_scene(gt, "pilot").tracks}
    tracks = []
    for a in model.agents:
        i = model.index[a.name]
        if not outcome.changed[i]:
            tracks.append(base[a.name])
            continue
        t, ref, h = behavior.poses(model, outcome, i)
        src = base[a.name]
        tracks.append(Track(a.name, src.category, t, ref, h, src.size, src.instance_token, src.bbox_center_x))
    return Scene(gt.name, gt.origin, gt.duration, tracks)


def grid_config() -> dict:
    return {"event_step_s": EVENT_STEP, "event_min_speed_mps": EVENT_SPEED, "decels_mps2": list(DECELS),
            "targets": [list(t) for t in TARGETS], "after_event_s": AFTER_EVENT, "follow_window_s": list(FOLLOW_WINDOW)}


def thresholds() -> dict:
    return {"reaction_s": behavior.REACTION, "idm_a": behavior.IDM_A, "idm_b": behavior.IDM_B,
            "max_decel": behavior.MAX_DECEL, "heavy_max_decel": behavior.HEAVY_MAX_DECEL, "jerk_brake": behavior.JERK_BRAKE, "jerk_normal": behavior.JERK_NORMAL,
            "T_default": behavior.T_DEFAULT, "T_range": list(behavior.T_RANGE), "s0_default": behavior.S0_DEFAULT,
            "s0_range": list(behavior.S0_RANGE), "lookahead_m": behavior.LOOKAHEAD,
            "corridor_margin_m": behavior.CORRIDOR_MARGIN, "watch_ahead": behavior.WATCH_AHEAD,
            "valid_max_accel": MAX_ACCEL, "valid_decel_slack": DECEL_SLACK, "label_reach_m": LABEL_REACH,
            "merge_lookback_s": MERGE_LOOKBACK, "tailgate_gap_m": TAILGATE_GAP,
            "tailgate_speed_mps": TAILGATE_SPEED, "tailgate_time_s": TAILGATE_TIME,
            "exempt_along_m": EXEMPT_ALONG, "exempt_across_m": EXEMPT_ACROSS, "exempt_depth_m": EXEMPT_DEPTH,
            "appear_window_s": APPEAR_WINDOW, "close_gap_m": CLOSE_GAP, "close_ttc_s": CLOSE_TTC,
            "close_gap_on_path_only": True,
            "comfort_decel": COMFORT_DECEL, "new_margin": NEW_MARGIN}


def replay_dynamics(model: SceneModel, outcome: Outcome, sim: dict) -> dict:
    """Largest acceleration of the changed agents in the simulation and in the esmini log (raw, and averaged
    over 0.2 s): a timed polyline makes esmini's speed constant per segment, so the log is less smooth."""
    def peak(t, xy, smooth):
        if len(t) < 2 * PHYSICS_SMOOTH:
            return 0.0
        s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
        v = np.gradient(s, t)
        if smooth:
            v = np.convolve(v, np.ones(PHYSICS_SMOOTH) / PHYSICS_SMOOTH, mode="valid")
            t = t[PHYSICS_SMOOTH // 2:PHYSICS_SMOOTH // 2 + len(v)]
        return float(np.abs(np.gradient(v, t)).max())

    out = {"sim": 0.0, "esmini_raw": 0.0, "esmini_smoothed": 0.0}
    for i in np.flatnonzero(outcome.changed):
        a = model.agents[i]
        t, ref, _ = behavior.poses(model, outcome, i)
        out["sim"] = max(out["sim"], peak(t, ref, True))
        st = sim.get(a.name)
        if st is not None and len(t):
            # only while it follows its trajectory: before the first vertex esmini holds it at the start pose,
            # after the last one at the end pose until the scenario stops (not motion)
            inner = (st.t >= t[0] + EDGE_SKIP) & (st.t <= t[-1] - EDGE_SKIP)
            out["esmini_raw"] = max(out["esmini_raw"], peak(st.t[inner], st.xy[inner], False))
            out["esmini_smoothed"] = max(out["esmini_smoothed"], peak(st.t[inner], st.xy[inner], True))
    return {k: round(v, 2) for k, v in out.items()}


# ---------------------------------------------------------------- summary
def summarize(rows: list[dict]) -> dict:
    reasons = {}
    for row in rows:
        for r in row["reasons"]:
            reasons[r] = reasons.get(r, 0) + 1
    valid = [r for r in rows if r["valid"]]
    groups = {g: sum(r["group"] == g for r in valid) for g in GROUPS}
    encounters = {r["encounter"] for r in rows}
    valid_enc = {r["encounter"] for r in valid}
    rare_enc = {r["encounter"] for r in valid if r["group"] in VALUABLE}
    return {
        "attempted": len(rows),
        "valid": len(valid),
        "valid_rate": len(valid) / len(rows) if rows else 0.0,
        "rejected_by": dict(sorted(reasons.items())),
        "encounters": len(encounters),
        "encounters_with_valid": len(valid_enc),
        "groups": groups,
        "valuable": sum(groups[g] for g in VALUABLE),
        "valuable_encounters": len(rare_enc),
        "strong_braking_events": sum(r["decel"] >= 6 for r in valid),
        "kept_xosc": sum(bool(r.get("kept")) for r in rows),
        "esmini_failed": reasons.get("esmini", 0),
    }


def format_summary(s: dict) -> str:
    return "\n".join([
        f"attempted {s['attempted']} variants in {s['encounters']} encounters; valid {s['valid']} "
        f"({100 * s['valid_rate']:.1f}%), encounters with a valid variant {s['encounters_with_valid']}",
        f"rejected by {s['rejected_by']}",
        f"ego groups {s['groups']}; valuable (hard + close) {s['valuable']} in {s['valuable_encounters']} encounters",
        f"valid variants using 6-8 m/s^2 braking: {s['strong_braking_events']}; .xosc kept {s['kept_xosc']}",
    ])
