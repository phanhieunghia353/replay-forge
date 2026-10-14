"""Held-out check of metric 1: are the reconstructions faithful between the labels, or do they only fit
the labels they were built from?

Every other keyframe of each moving track is hidden; the three reconstructions are rebuilt from the kept
ones and their error is measured on the hidden ones only (the first and last keyframes are always kept).
esmini is not run: replaying a reconstruction changes it by about 0.001 m (metric 1, method "exact"), far
below the differences measured here.

  exact     straight lines between the kept labels (what replaying the labels point by point gives)
  baseline  one constant speed along the kept labels' path
  pilot     smoothed path, speed knots every 2 s (as in metric 1)

It also measures how smooth each reconstruction of the full labels is: the 99th percentile of |acceleration|
along the track, sampled every SMOOTH_DT. Straight lines between noisy labels fit them best but jerk.
"""

from __future__ import annotations

import numpy as np

from real2sim.abstraction import METHODS, reconstruct
from real2sim.tracks import Scene, Track

MIN_KEYFRAMES = 5  # tracks with fewer labels are left out (nothing meaningful to hide)
SMOOTH_DT = 0.05  # s, sampling step for the smoothness measure (esmini's step)
ACCEL_LIMIT = 4.0  # m/s^2, the share of tracks whose peak acceleration exceeds this is reported


def split(track: Track) -> tuple[Track, np.ndarray]:
    """(the track with every other keyframe removed, indices of the hidden keyframes)."""
    n = len(track.t)
    keep = np.zeros(n, bool)
    keep[::2] = True
    keep[-1] = True
    kept = Track(track.name, track.category, track.t[keep], track.xy[keep], track.yaw[keep], track.size,
                 track.instance_token, track.bbox_center_x)
    return kept, np.flatnonzero(~keep)


def holdout_scene(gt: Scene) -> dict:
    """Per moving track and method: mean distance (m) at the hidden keyframes; and the per-method mean
    over tracks (each track counts once, as in metric 1)."""
    tracks, hidden = [], {}
    for track in gt.tracks:
        if track.is_stationary or len(track.t) < MIN_KEYFRAMES:
            continue
        kept, idx = split(track)
        if not len(idx):
            continue
        tracks.append(kept)
        hidden[track.name] = (track.t[idx], track.xy[idx])
    reduced = Scene(gt.name, gt.origin, gt.duration, tracks)
    per_track = {name: {} for name in hidden}
    for method in METHODS:
        for rec in reconstruct(reduced, method).tracks:
            t, xy = hidden[rec.name]
            x = np.interp(t, rec.t, rec.xy[:, 0])
            y = np.interp(t, rec.t, rec.xy[:, 1])
            d = np.hypot(x - xy[:, 0], y - xy[:, 1])
            per_track[rec.name][method] = {"ade": float(d.mean()), "max": float(d.max()), "n": int(len(d))}
    summary = {m: (float(np.mean([v[m]["ade"] for v in per_track.values()])) if per_track else None) for m in METHODS}
    return {"scene": gt.name, "tracks": len(per_track), "summary": summary, "per_track": per_track,
            "smoothness": smoothness(gt)}


def peak_accel(track: Track) -> float | None:
    """99th percentile of |acceleration| along a track sampled every SMOOTH_DT (None when too short)."""
    t = np.arange(track.t[0], track.t[-1], SMOOTH_DT)
    if len(t) < 10:
        return None
    x, y = np.interp(t, track.t, track.xy[:, 0]), np.interp(t, track.t, track.xy[:, 1])
    v = np.hypot(np.diff(x), np.diff(y)) / SMOOTH_DT
    return float(np.percentile(np.abs(np.diff(v) / SMOOTH_DT), 99))


def smoothness(gt: Scene) -> dict:
    """Per method, over the moving tracks with at least MIN_KEYFRAMES labels: the peak acceleration of each
    track (full labels, no hiding)."""
    out = {}
    for method in METHODS:
        peaks = {}
        for rec in reconstruct(gt, method).tracks:
            if rec.is_stationary or len(rec.t) < 2:
                continue
            original = next(t for t in gt.tracks if t.name == rec.name)
            if original.is_stationary or len(original.t) < MIN_KEYFRAMES:
                continue
            value = peak_accel(rec)
            if value is not None:
                peaks[rec.name] = round(value, 3)
        out[method] = peaks
    return out
