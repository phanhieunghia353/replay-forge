"""Box geometry, physical plausibility and criticality measures on sampled trajectories.

States are sampled on a common time grid. Boxes are oriented rectangles in the ground plane; the
box centre lies bbox_center_x ahead of the trajectory reference point along the heading.

ttc   time to collision under constant velocity: both boxes are moved along their current velocity
      (heading kept) for up to TTC_HORIZON seconds; TTC is the first time their boxes overlap
      (0 if they overlap now, inf if not within the horizon).
gap   smallest distance between the two box outlines (0 when they overlap).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GRID_DT = 0.1  # s
TTC_HORIZON = 5.0  # s
TTC_STEP = 0.1  # s


@dataclass
class BoxTrack:
    """Box centre, heading and velocity of one object on a time grid."""

    t: np.ndarray
    centre: np.ndarray  # (N, 2)
    heading: np.ndarray  # (N,)
    velocity: np.ndarray  # (N, 2)
    length: float
    width: float


def box_track(t, ref_xy, heading, length, width, bbox_center_x=0.0) -> BoxTrack:
    t, ref_xy, heading = np.asarray(t, float), np.asarray(ref_xy, float), np.asarray(heading, float)
    centre = ref_xy + bbox_center_x * np.column_stack([np.cos(heading), np.sin(heading)])
    if len(t) > 1:
        velocity = np.column_stack([np.gradient(centre[:, k], t) for k in (0, 1)])
    else:
        velocity = np.zeros_like(centre)
    return BoxTrack(t, centre, heading, velocity, float(length), float(width))


def corners(centre: np.ndarray, heading: np.ndarray, length: float, width: float) -> np.ndarray:
    """(..., 4, 2) corners, counter-clockwise from rear-right."""
    c, s = np.cos(heading)[..., None], np.sin(heading)[..., None]
    lx = np.array([-1, 1, 1, -1]) * length / 2
    ly = np.array([-1, -1, 1, 1]) * width / 2
    x = centre[..., 0:1] + c * lx - s * ly
    y = centre[..., 1:2] + s * lx + c * ly
    return np.stack([x, y], axis=-1)


def _axes(box: np.ndarray) -> np.ndarray:
    edges = np.stack([box[..., 1, :] - box[..., 0, :], box[..., 3, :] - box[..., 0, :]], axis=-2)
    return edges / np.linalg.norm(edges, axis=-1, keepdims=True)


def overlap(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Separating-axis test for two arrays of rectangles (..., 4, 2) -> bool (...)."""
    axes = np.concatenate([_axes(a), _axes(b)], axis=-2)  # (..., 4, 2)
    pa = np.einsum("...ck,...ak->...ac", a, axes)
    pb = np.einsum("...ck,...ak->...ac", b, axes)
    separated = (pa.max(-1) < pb.min(-1)) | (pb.max(-1) < pa.min(-1))
    return ~separated.any(-1)


def _point_segment(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    """Distances (..., P, S) from points (..., P, 2) to segments (..., S, 2)."""
    d = (end - start)[..., None, :, :]
    w = points[..., :, None, :] - start[..., None, :, :]
    u = np.clip((w * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-12), 0, 1)
    return np.linalg.norm(w - u[..., None] * d, axis=-1)


def gap(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Smallest distance between rectangle outlines (..., 4, 2); 0 where they overlap."""
    a_end, b_end = np.roll(a, -1, axis=-2), np.roll(b, -1, axis=-2)
    dist = np.minimum(_point_segment(a, b, b_end).min((-1, -2)), _point_segment(b, a, a_end).min((-1, -2)))
    return np.where(overlap(a, b), 0.0, dist)


def resample(box: BoxTrack, t: np.ndarray) -> BoxTrack:
    """Values at times t (inside box.t), linear in position, velocity and unwrapped heading."""
    interp = lambda v: np.interp(t, box.t, v)  # noqa: E731
    centre = np.column_stack([interp(box.centre[:, 0]), interp(box.centre[:, 1])])
    velocity = np.column_stack([interp(box.velocity[:, 0]), interp(box.velocity[:, 1])])
    return BoxTrack(t, centre, interp(np.unwrap(box.heading)), velocity, box.length, box.width)


def common_times(a: BoxTrack, b: BoxTrack, dt: float = GRID_DT) -> np.ndarray:
    t0, t1 = max(a.t[0], b.t[0]), min(a.t[-1], b.t[-1])
    if t1 < t0:
        return np.empty(0)
    return np.arange(t0, t1 + 1e-9, dt)


def pair_measures(a: BoxTrack, b: BoxTrack, with_ttc: bool = True) -> dict:
    """Overlap, gap and TTC over the time both objects are present."""
    t = common_times(a, b)
    if len(t) == 0:
        return {"t": t, "overlap": np.zeros(0, bool), "gap": np.zeros(0), "ttc": np.zeros(0)}
    ra, rb = resample(a, t), resample(b, t)
    ca = corners(ra.centre, ra.heading, a.length, a.width)
    cb = corners(rb.centre, rb.heading, b.length, b.width)
    now = overlap(ca, cb)
    if not with_ttc:
        return {"t": t, "overlap": now}
    horizon = np.arange(TTC_STEP, TTC_HORIZON + 1e-9, TTC_STEP)  # (K,)
    pa = ra.centre[:, None, :] + ra.velocity[:, None, :] * horizon[None, :, None]
    pb = rb.centre[:, None, :] + rb.velocity[:, None, :] * horizon[None, :, None]
    ha = np.broadcast_to(ra.heading[:, None], pa.shape[:2])
    hb = np.broadcast_to(rb.heading[:, None], pb.shape[:2])
    future = overlap(corners(pa, ha, a.length, a.width), corners(pb, hb, b.length, b.width))  # (N, K)
    first = np.where(future.any(1), horizon[np.argmax(future, axis=1)], np.inf)
    return {"t": t, "overlap": now, "gap": gap(ca, cb), "ttc": np.where(now, 0.0, first)}


def braked_poses(box: BoxTrack, t_brake: float, decels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Box centres (A, N, 2) and headings (A, N) on box.t when the object keeps its recorded path but,
    from t_brake on, drives at v(t) = min(v_rec(t), v_rec(t_brake) - a (t - t_brake)), never below 0;
    one row per deceleration a. Braking starts at the first sample at or after t_brake."""
    t = box.t
    step = np.hypot(*np.diff(box.centre, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(step)])
    v_rec = np.gradient(s, t) if len(t) > 1 else np.zeros_like(t)
    k0 = int(np.searchsorted(t, t_brake - 1e-9))
    decels = np.asarray(decels, float)
    out_s = np.tile(s, (len(decels), 1))
    if k0 < len(t):
        v = np.minimum(v_rec[None, k0:], v_rec[k0] - decels[:, None] * (t[None, k0:] - t[k0]))
        v = np.clip(v, 0.0, None)
        travelled = np.concatenate([np.zeros((len(decels), 1)),
                                    np.cumsum(0.5 * (v[:, 1:] + v[:, :-1]) * np.diff(t[k0:]), axis=1)], axis=1)
        out_s[:, k0:] = np.minimum(s[k0] + travelled, s[None, k0:])  # never ahead of the recording
    keep = np.concatenate([[True], step > 1e-6])
    sk, heading = s[keep], np.unwrap(box.heading)[keep]
    if len(sk) == 1:
        centre = np.broadcast_to(box.centre[0], (*out_s.shape, 2)).copy()
        return centre, np.full(out_s.shape, heading[0])
    centre = np.stack([np.interp(out_s, sk, box.centre[keep, k]) for k in (0, 1)], axis=-1)
    return centre, np.interp(out_s, sk, heading)


def braking_avoids(ego: BoxTrack, actor: BoxTrack, t_brake: float, decels: np.ndarray,
                   ignore: np.ndarray | None = None, ignore_dt: float = 0.0) -> np.ndarray:
    """For each deceleration: True when the braking ego's box overlaps the actor's at no time from
    t_brake on (ego log times inside the actor's span), apart from times within ignore_dt of `ignore`."""
    centre, heading = braked_poses(ego, t_brake, decels)
    mask = (ego.t >= t_brake - 1e-9) & (ego.t >= actor.t[0] - 1e-9) & (ego.t <= actor.t[-1] + 1e-9)
    if ignore is not None and len(ignore):
        mask &= np.abs(ego.t[:, None] - np.asarray(ignore)[None, :]).min(axis=1) > ignore_dt
    if not mask.any():
        return np.ones(len(decels), bool)
    t = ego.t[mask]
    other = resample(actor, t)
    cb = corners(other.centre, other.heading, actor.length, actor.width)
    ca = corners(centre[:, mask], heading[:, mask], ego.length, ego.width)
    return ~overlap(ca, np.broadcast_to(cb, ca.shape)).any(axis=1)


def path_ttc(ego: BoxTrack, other: BoxTrack, t: np.ndarray) -> np.ndarray:
    """TTC at times t when the ego keeps its current speed along its own recorded path (a driver knows
    the road ahead) and the other object keeps its current velocity in a straight line (its intentions
    are unknown). inf when no overlap within TTC_HORIZON; 0 when the boxes overlap now."""
    t = np.asarray(t, float)
    step = np.hypot(*np.diff(ego.centre, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(step)])
    keep = np.concatenate([[True], step > 1e-6])
    sk, ck, hk = s[keep], ego.centre[keep], np.unwrap(ego.heading)[keep]
    speed = np.hypot(*ego.velocity.T)
    s_now, v_now = np.interp(t, ego.t, s), np.interp(t, ego.t, speed)
    horizon = np.arange(0.0, TTC_HORIZON + 1e-9, TTC_STEP)  # (K,), 0 = now
    s_future = s_now[:, None] + v_now[:, None] * horizon[None, :]
    if len(sk) > 1:
        pe = np.stack([np.interp(s_future, sk, ck[:, k]) for k in (0, 1)], axis=-1)
        he = np.interp(s_future, sk, hk)
    else:
        pe, he = np.broadcast_to(ck[0], (*s_future.shape, 2)), np.full(s_future.shape, hk[0])
    ro = resample(other, t)
    po = ro.centre[:, None, :] + ro.velocity[:, None, :] * horizon[None, :, None]
    ho = np.broadcast_to(ro.heading[:, None], s_future.shape)
    hit = overlap(corners(pe, he, ego.length, ego.width), corners(po, ho, other.length, other.width))
    return np.where(hit.any(1), horizon[np.argmax(hit, axis=1)], np.inf)


def side_of(a: BoxTrack, b: BoxTrack, t: float) -> str:
    """Where a's box centre lies around b at time t, seen from b's heading: front, rear, left or right
    (sectors split at 45 and 135 degrees)."""
    ra, rb = resample(a, np.array([t])), resample(b, np.array([t]))
    dx, dy = ra.centre[0] - rb.centre[0]
    c, s = np.cos(rb.heading[0]), np.sin(rb.heading[0])
    angle = np.degrees(np.arctan2(-s * dx + c * dy, c * dx + s * dy))
    if abs(angle) <= 45:
        return "front"
    if abs(angle) >= 135:
        return "rear"
    return "left" if angle > 0 else "right"


def dynamics(box: BoxTrack, dt: float = GRID_DT) -> dict:
    """Peak speed and peak acceleration magnitude (longitudinal and lateral) on a dt grid."""
    if box.t[-1] - box.t[0] < 2 * dt:
        return {"max_speed": 0.0, "max_accel": 0.0}
    t = np.arange(box.t[0], box.t[-1] + 1e-9, dt)
    centre = np.column_stack([np.interp(t, box.t, box.centre[:, k]) for k in (0, 1)])
    velocity = np.diff(centre, axis=0) / dt
    accel = np.diff(velocity, axis=0) / dt
    return {
        "max_speed": float(np.linalg.norm(velocity, axis=1).max()),
        "max_accel": float(np.linalg.norm(accel, axis=1).max()) if len(accel) else 0.0,
    }
