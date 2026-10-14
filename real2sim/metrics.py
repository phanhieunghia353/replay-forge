"""Replay error: simulated states compared with the raw nuScenes poses at keyframe times.

Per track, over the keyframes inside the track's annotated time span:
  ade       mean 2D position error (m)
  fde       2D position error at the last keyframe (m)
  max       largest 2D position error (m)
  yaw_mae   mean absolute heading error (deg)
  speed_rmse  RMSE between keyframe-difference speed and simulated speed at interval midpoints (m/s)
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from real2sim.esmini import SimTrack
from real2sim.tracks import Track


def _wrap(angle: np.ndarray) -> np.ndarray:
    return (angle + np.pi) % (2 * np.pi) - np.pi


def track_errors(gt: Track, sim: SimTrack) -> dict:
    x = np.interp(gt.t, sim.t, sim.xy[:, 0])
    y = np.interp(gt.t, sim.t, sim.xy[:, 1])
    yaw = np.interp(gt.t, sim.t, np.unwrap(sim.yaw))
    dist = np.hypot(x - gt.xy[:, 0], y - gt.xy[:, 1])
    result = {
        "n": int(len(gt.t)),
        "ade": float(dist.mean()),
        "fde": float(dist[-1]),
        "max": float(dist.max()),
        "yaw_mae": float(np.degrees(np.abs(_wrap(yaw - gt.yaw))).mean()),
        "speed_rmse": None,
    }
    if len(gt.t) >= 2:
        dt = np.diff(gt.t)
        gt_speed = np.hypot(*np.diff(gt.xy, axis=0).T) / dt
        sim_speed = np.interp(gt.t[:-1] + dt / 2, sim.t, sim.speed)
        result["speed_rmse"] = float(np.sqrt(np.mean((np.abs(sim_speed) - gt_speed) ** 2)))
    return result


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def evaluate(tracks: list[Track], sim: dict[str, SimTrack]) -> dict:
    per_track, missing = {}, []
    for track in tracks:
        if track.name not in sim:
            missing.append(track.name)
            continue
        per_track[track.name] = {"kind": track.kind, "static": track.is_stationary,
                                 **track_errors(track, sim[track.name])}

    groups = defaultdict(list)
    for row in per_track.values():
        groups["all"].append(row)
        groups["moving" if not row["static"] else "static"].append(row)
        groups[f"kind:{row['kind']}"].append(row)
    summary = {
        name: {
            "tracks": len(rows),
            **{key: _mean([row[key] for row in rows]) for key in ("ade", "fde", "max", "yaw_mae", "speed_rmse")},
            "worst_max": max(row["max"] for row in rows),
        }
        for name, rows in groups.items()
    }
    return {"summary": summary, "per_track": per_track, "missing": missing}


def format_comparison(summaries: dict[str, dict], key: str = "ade") -> str:
    """One row per group, one column per method."""
    methods = list(summaries)
    groups = list(dict.fromkeys(g for summary in summaries.values() for g in summary))
    lines = [f"{key + ' (m)':<18}{'tracks':>7}" + "".join(f"{m:>12}" for m in methods)]
    for group in groups:
        rows = [summaries[m].get(group) for m in methods]
        tracks = next(row["tracks"] for row in rows if row)
        cells = "".join(f"{row[key]:>12.3f}" if row and row[key] is not None else f"{'-':>12}" for row in rows)
        lines.append(f"{group:<18}{tracks:>7}{cells}")
    return "\n".join(lines)


def format_summary(summary: dict) -> str:
    def cell(value):
        return "-" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value:.3f}"

    lines = [f"{'group':<18}{'tracks':>7}{'ADE m':>9}{'FDE m':>9}{'max m':>9}{'yaw deg':>9}{'v RMSE':>9}"]
    for name, row in summary.items():
        lines.append(
            f"{name:<18}{row['tracks']:>7}{cell(row['ade']):>9}{cell(row['fde']):>9}"
            f"{cell(row['max']):>9}{cell(row['yaw_mae']):>9}{cell(row['speed_rmse']):>9}"
        )
    return "\n".join(lines)
