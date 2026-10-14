"""Turn nuScenes annotations and ego poses into per-object trajectories in a scene-local frame.

Scene-local frame: global nuScenes axes (x east, y north, z up, metres), shifted so that the
ego position at the first keyframe is (0, 0). Time 0 is the first keyframe of the scene.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from real2sim.nuscenes_io import NuScenesTables

# Renault Zoe used for nuScenes data collection. Assumption, not given by the dataset tables.
EGO_SIZE = (4.084, 1.730, 1.562)
# nuScenes ego frame sits at the rear axle; box centre is ~1.39 m ahead (assumption from Zoe specs).
EGO_BBOX_CENTER_X = 1.39
EGO_WHEELBASE = 2.588  # Renault Zoe, assumption
WHEELBASE_RATIO = 0.6  # wheelbase / length for annotated vehicles, assumption
# A track whose poses all stay within this distance of their mean is treated as not moving. Box
# placement error grows with object size, so long vehicles get a larger allowance. Assumptions.
STATIONARY_EXTENT = 1.0  # m
STATIONARY_LENGTH_RATIO = 0.25

VEHICLE_CATEGORIES = {
    "vehicle.ego": "car",
    "vehicle.car": "car",
    "vehicle.emergency.police": "car",
    "vehicle.emergency.ambulance": "van",
    "vehicle.motorcycle": "motorbike",
    "vehicle.bicycle": "bicycle",
    "vehicle.bus.bendy": "bus",
    "vehicle.bus.rigid": "bus",
    "vehicle.truck": "truck",
    "vehicle.construction": "truck",
    "vehicle.trailer": "trailer",
}


def entity_class(category: str) -> tuple[str, str]:
    """nuScenes category -> (OpenSCENARIO entity kind, OpenSCENARIO category)."""
    if category in VEHICLE_CATEGORIES:
        return "vehicle", VEHICLE_CATEGORIES[category]
    if category.startswith("human.pedestrian"):
        return "pedestrian", "pedestrian"
    if category.startswith("animal"):
        return "pedestrian", "animal"
    if category == "movable_object.barrier":
        return "misc", "barrier"
    return "misc", "obstacle"


def quaternion_yaw(q) -> float:
    """Yaw (rad) of a (w, x, y, z) quaternion."""
    w, x, y, z = q
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


@dataclass
class Track:
    name: str
    category: str
    t: np.ndarray  # (N,) seconds from scene start
    xy: np.ndarray  # (N, 2) scene-local metres, reference point
    yaw: np.ndarray  # (N,) rad, world frame
    size: tuple[float, float, float]  # length, width, height
    instance_token: str | None = None
    bbox_center_x: float = 0.0  # box centre ahead of the reference point, metres

    @property
    def kind(self) -> str:
        return entity_class(self.category)[0]

    @property
    def is_static(self) -> bool:
        """True when the track has a single pose or every pose is identical."""
        return len(self.t) < 2 or bool(np.all(self.xy == self.xy[0]))

    @property
    def is_stationary(self) -> bool:
        """True when every pose lies close to the mean position (label jitter only)."""
        limit = max(STATIONARY_EXTENT, STATIONARY_LENGTH_RATIO * self.size[0])
        return bool(np.hypot(*(self.xy - self.xy.mean(axis=0)).T).max() < limit)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "instance_token": self.instance_token,
            "size": list(self.size),
            "bbox_center_x": self.bbox_center_x,
            "t": self.t.tolist(),
            "xy": self.xy.tolist(),
            "yaw": self.yaw.tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(
            name=data["name"],
            category=data["category"],
            t=np.asarray(data["t"], dtype=float),
            xy=np.asarray(data["xy"], dtype=float).reshape(-1, 2),
            yaw=np.asarray(data["yaw"], dtype=float),
            size=tuple(data["size"]),
            instance_token=data.get("instance_token"),
            bbox_center_x=data.get("bbox_center_x", 0.0),
        )


@dataclass
class Scene:
    name: str
    origin: tuple[float, float]  # global xy subtracted to form the scene-local frame
    duration: float
    tracks: list[Track] = field(default_factory=list)  # ego first

    def save(self, path: str | Path) -> None:
        data = {
            "name": self.name,
            "origin": list(self.origin),
            "duration": self.duration,
            "tracks": [track.to_dict() for track in self.tracks],
        }
        Path(path).write_text(json.dumps(data, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Scene":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            name=data["name"],
            origin=tuple(data["origin"]),
            duration=data["duration"],
            tracks=[Track.from_dict(row) for row in data["tracks"]],
        )


def extract_scene(nusc: NuScenesTables, scene_name: str) -> Scene:
    """Raw keyframe (2 Hz) trajectories of the ego and of every annotated instance."""
    samples = nusc.samples(scene_name)
    t0 = samples[0]["timestamp"]
    poses = [nusc.keyframe_ego_pose(sample["token"]) for sample in samples]
    origin = np.asarray(poses[0]["translation"][:2], dtype=float)

    ego = Track(
        name="ego",
        category="vehicle.ego",
        t=np.array([(pose["timestamp"] - t0) * 1e-6 for pose in poses]),
        xy=np.array([pose["translation"][:2] for pose in poses], dtype=float) - origin,
        yaw=np.array([quaternion_yaw(pose["rotation"]) for pose in poses]),
        size=EGO_SIZE,
        bbox_center_x=EGO_BBOX_CENTER_X,
    )

    by_instance = defaultdict(list)
    for sample in samples:
        for ann in nusc.annotations(sample["token"]):
            by_instance[ann["instance_token"]].append(((sample["timestamp"] - t0) * 1e-6, ann))

    raw = []
    for instance_token, rows in by_instance.items():
        rows.sort(key=lambda row: row[0])
        anns = [ann for _, ann in rows]
        width, length, height = np.median(np.array([ann["size"] for ann in anns], dtype=float), axis=0)
        raw.append(
            (
                rows[0][0],
                Track(
                    name="",
                    category=nusc.category_name(anns[0]),
                    t=np.array([t for t, _ in rows]),
                    xy=np.array([ann["translation"][:2] for ann in anns], dtype=float) - origin,
                    yaw=np.array([quaternion_yaw(ann["rotation"]) for ann in anns]),
                    size=(float(length), float(width), float(height)),
                    instance_token=instance_token,
                ),
            )
        )
    raw.sort(key=lambda row: (row[0], row[1].category, row[1].instance_token))

    counters = defaultdict(int)
    tracks = [ego]
    for _, track in raw:
        short = entity_class(track.category)[1]
        counters[short] += 1
        track.name = f"{short}_{counters[short]:03d}"
        tracks.append(track)

    duration = (samples[-1]["timestamp"] - t0) * 1e-6
    return Scene(scene_name, (float(origin[0]), float(origin[1])), duration, tracks)
