"""Read the nuScenes JSON tables needed for trajectory extraction, without the devkit."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

TABLES = (
    "scene",
    "sample",
    "sample_data",
    "ego_pose",
    "calibrated_sensor",
    "sensor",
    "sample_annotation",
    "instance",
    "category",
)
OPTIONAL_TABLES = ("log",)


class NuScenesError(RuntimeError):
    pass


class NuScenesTables:
    def __init__(self, dataroot: str | Path, version: str = "v1.0-mini"):
        self.root = Path(dataroot)
        base = self.root / version
        if not base.is_dir():
            raise NuScenesError(f"Missing nuScenes table directory: {base}")
        self.tables: dict[str, dict[str, dict]] = {}
        for name in TABLES:
            path = base / f"{name}.json"
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise NuScenesError(f"Cannot read {path}: {exc}") from exc
            self.tables[name] = {row["token"]: row for row in rows}
        for name in OPTIONAL_TABLES:
            path = base / f"{name}.json"
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
            self.tables[name] = {row["token"]: row for row in rows}

        self._scenes = {row["name"]: row for row in self.tables["scene"].values()}
        self._samples = defaultdict(list)
        for row in self.tables["sample"].values():
            self._samples[row["scene_token"]].append(row)
        for rows in self._samples.values():
            rows.sort(key=lambda row: row["timestamp"])
        self._annotations = defaultdict(list)
        for row in self.tables["sample_annotation"].values():
            self._annotations[row["sample_token"]].append(row)
        self._lidar_key = {}
        for row in self.tables["sample_data"].values():
            if row["is_key_frame"] and self.channel(row) == "LIDAR_TOP":
                self._lidar_key[row["sample_token"]] = row

    def channel(self, sample_data: dict) -> str:
        calib = self.tables["calibrated_sensor"][sample_data["calibrated_sensor_token"]]
        return self.tables["sensor"][calib["sensor_token"]]["channel"]

    def scene_names(self) -> list[str]:
        return sorted(self._scenes)

    def samples(self, scene_name: str) -> list[dict]:
        try:
            scene = self._scenes[scene_name]
        except KeyError as exc:
            raise NuScenesError(f"Unknown scene: {scene_name}") from exc
        samples = self._samples[scene["token"]]
        if not samples:
            raise NuScenesError(f"Scene has no samples: {scene_name}")
        return samples

    def scene_description(self, scene_name: str) -> str:
        return self._scenes[scene_name].get("description", "")

    def scene_location(self, scene_name: str) -> str | None:
        """Map name of the scene's log (e.g. 'singapore-onenorth'), None if log.json is absent."""
        log = self.tables["log"].get(self._scenes[scene_name].get("log_token"))
        return log["location"] if log else None

    def annotations(self, sample_token: str) -> list[dict]:
        return self._annotations[sample_token]

    def category_name(self, annotation: dict) -> str:
        instance = self.tables["instance"][annotation["instance_token"]]
        return self.tables["category"][instance["category_token"]]["name"]

    def keyframe_ego_pose(self, sample_token: str) -> dict:
        """Ego pose of the LIDAR_TOP keyframe of a sample (nuScenes ego frame = rear axle centre)."""
        try:
            lidar = self._lidar_key[sample_token]
        except KeyError as exc:
            raise NuScenesError(f"Sample has no LIDAR_TOP keyframe: {sample_token}") from exc
        return self.tables["ego_pose"][lidar["ego_pose_token"]]
