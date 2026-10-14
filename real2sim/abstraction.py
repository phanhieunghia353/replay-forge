"""Reconstructions of annotated tracks that a scenario replays.

exact     the keyframe poses as recorded. Replay error is ~0 by construction: a pipeline check only.
baseline  "abstracted" coarsely: the raw keyframe path, driven at one constant speed over the
          track's annotated time span.
pilot     "abstracted" carefully: stationary objects pinned to their mean pose; otherwise a smoothed
          path (smoothing spline, lambda by generalised cross-validation) driven with a speed profile
          that has one knot every KNOT_SPACING seconds. Arc length between knots follows a monotone
          cubic (PCHIP), so the speed is continuous and never negative.

The speed profile is the part a variant edits (speed factor, start time), so the replay error of an
abstraction measures how much of the real motion its few parameters keep.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.interpolate import PchipInterpolator, make_smoothing_spline

from real2sim.tracks import Scene, Track

METHODS = ("exact", "baseline", "pilot")
DT = 0.1  # s, vertex spacing of reconstructed trajectories
KNOT_SPACING = 2.0  # s, pilot speed profile
MIN_SPLINE_POINTS = 5  # scipy make_smoothing_spline needs at least 5 samples
MIN_HEADING_SPEED = 0.5  # m/s, below this the heading comes from the box yaw, not the motion


def _dense_times(t: np.ndarray) -> np.ndarray:
    td = np.arange(t[0], t[-1], DT)
    return np.append(td, t[-1])


def _wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


def with_poses(track: Track, t, xy, yaw) -> Track:
    return Track(track.name, track.category, np.asarray(t, float), np.asarray(xy, float).reshape(-1, 2),
                 np.asarray(yaw, float), track.size, track.instance_token, track.bbox_center_x)


def drive_along(t_out: np.ndarray, s_out: np.ndarray, s: np.ndarray, xy: np.ndarray, yaw: np.ndarray):
    """Poses at arc lengths s_out along a path sampled at arc lengths s (non-decreasing)."""
    keep = np.concatenate([[True], np.diff(s) > 1e-6])
    s, xy, yaw = s[keep], xy[keep], np.unwrap(yaw)[keep]
    if len(s) == 1:
        return t_out, np.tile(xy[0], (len(t_out), 1)), np.full(len(t_out), yaw[0])
    pos = np.column_stack([np.interp(s_out, s, xy[:, k]) for k in (0, 1)])
    return t_out, pos, np.interp(s_out, s, yaw)


def arc_length(xy: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])


def baseline(track: Track) -> Track:
    if track.is_static:
        return track
    s = arc_length(track.xy)
    td = _dense_times(track.t)
    s_out = s[-1] * (td - track.t[0]) / (track.t[-1] - track.t[0])
    return with_poses(track, *drive_along(td, s_out, s, track.xy, track.yaw))


def smooth_path(track: Track) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dense smoothed poses. Heading follows the motion (or its reverse, when the box points
    backwards along it) above MIN_HEADING_SPEED, and the smoothed box yaw below it."""
    td = _dense_times(track.t)
    yaw_unwrapped = np.unwrap(track.yaw)
    if len(track.t) < MIN_SPLINE_POINTS:
        xy = np.column_stack([np.interp(td, track.t, track.xy[:, k]) for k in (0, 1)])
        return td, xy, np.interp(td, track.t, yaw_unwrapped)
    sx, sy = (make_smoothing_spline(track.t, track.xy[:, k]) for k in (0, 1))
    box_yaw = make_smoothing_spline(track.t, yaw_unwrapped)(td)
    vx, vy = sx.derivative()(td), sy.derivative()(td)
    motion = np.arctan2(vy, vx)
    reverse = np.abs(_wrap(motion - box_yaw)) > math.pi / 2
    motion = np.where(reverse, motion + math.pi, motion)
    heading = np.where(np.hypot(vx, vy) > MIN_HEADING_SPEED, motion, box_yaw)
    heading = box_yaw + _wrap(heading - box_yaw)
    return td, np.column_stack([sx(td), sy(td)]), heading


def pilot(track: Track) -> Track:
    if track.is_stationary:
        # the same pose at the first and last annotation keeps the time span the object is present
        centre = track.xy.mean(axis=0)
        yaw = math.atan2(np.sin(track.yaw).mean(), np.cos(track.yaw).mean())
        t = track.t[[0, -1]] if len(track.t) > 1 else track.t[:1]
        return with_poses(track, t, np.tile(centre, (len(t), 1)), np.full(len(t), yaw))
    td, xy, yaw = smooth_path(track)
    s = arc_length(xy)
    knots = np.arange(td[0], td[-1], KNOT_SPACING)
    knots = np.append(knots, td[-1])
    s_out = PchipInterpolator(knots, np.interp(knots, td, s))(td)
    return with_poses(track, *drive_along(td, s_out, s, xy, yaw))


def reconstruct(scene: Scene, method: str) -> Scene:
    if method not in METHODS:
        raise ValueError(f"Unknown method {method!r}, expected one of {METHODS}")
    fn = {"exact": lambda track: track, "baseline": baseline, "pilot": pilot}[method]
    return Scene(scene.name, scene.origin, scene.duration, [fn(track) for track in scene.tracks])
