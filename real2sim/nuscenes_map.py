"""Read the nuScenes map expansion (v1.3) JSON without the devkit.

Lane and lane-connector centrelines are stored in `arcline_path_3` as Dubins-style paths: each
element has a start pose (x, y, yaw), a three-letter shape over {L, S, R} (left arc, straight,
right arc), one radius and three segment lengths. Coordinates are in the same global frame as the
nuScenes ego poses and annotations.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CURVATURE_SIGN = {"L": 1.0, "S": 0.0, "R": -1.0}
MIN_SEGMENT = 1e-4  # m, shorter segments are dropped
MIN_LANE_WIDTH, MAX_LANE_WIDTH = 2.5, 5.0  # m, clamp for widths estimated from polygons
DEFAULT_LANE_WIDTH = 3.5  # m, when the lane polygon is missing


@dataclass
class Primitive:
    """One planView geometry: start pose, length and constant curvature (0 = line)."""

    x: float
    y: float
    hdg: float
    length: float
    curvature: float


@dataclass
class MapLane:
    token: str
    kind: str  # "lane" or "lane_connector"
    primitives: list[Primitive]
    width: float

    @property
    def length(self) -> float:
        return sum(p.length for p in self.primitives)


def advance(x: float, y: float, hdg: float, length: float, curvature: float) -> tuple[float, float, float]:
    """End pose after driving `length` with constant `curvature` from (x, y, hdg)."""
    if abs(curvature) < 1e-12:
        return x + length * math.cos(hdg), y + length * math.sin(hdg), hdg
    end = hdg + curvature * length
    return (x + (math.sin(end) - math.sin(hdg)) / curvature,
            y - (math.cos(end) - math.cos(hdg)) / curvature, end)


def arcline_primitives(path: list[dict]) -> list[Primitive]:
    out = []
    for element in path:
        x, y, hdg = element["start_pose"]
        for letter, length in zip(element["shape"], element["segment_length"]):
            curvature = CURVATURE_SIGN[letter] / element["radius"]
            if length >= MIN_SEGMENT:
                out.append(Primitive(x, y, hdg, length, curvature))
            x, y, hdg = advance(x, y, hdg, length, curvature)
    return out


def polygon_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


class MapExpansion:
    def __init__(self, dataroot: str | Path, location: str):
        path = Path(dataroot) / "maps" / "expansion" / f"{location}.json"
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.location = location
        self.nodes = {row["token"]: (row["x"], row["y"]) for row in self.data["node"]}
        self.polygons = {row["token"]: row for row in self.data["polygon"]}

    def polygon(self, token: str) -> tuple[np.ndarray, list[np.ndarray]]:
        """Exterior ring and hole rings as (N, 2) arrays."""
        row = self.polygons[token]
        exterior = np.array([self.nodes[n] for n in row["exterior_node_tokens"]], dtype=float)
        holes = [np.array([self.nodes[n] for n in hole["node_tokens"]], dtype=float) for hole in row["holes"]]
        return exterior, holes

    def lanes(self, xmin: float, ymin: float, xmax: float, ymax: float) -> list[MapLane]:
        """Lanes and lane connectors with a centreline point inside the box (global frame)."""
        out = []
        for kind in ("lane", "lane_connector"):
            for row in self.data[kind]:
                path = self.data["arcline_path_3"].get(row["token"])
                if not path:
                    continue
                poses = np.array([p for e in path for p in (e["start_pose"], e["end_pose"])], dtype=float)
                inside = (poses[:, 0] >= xmin) & (poses[:, 0] <= xmax) & (poses[:, 1] >= ymin) & (poses[:, 1] <= ymax)
                if not inside.any():
                    continue
                primitives = arcline_primitives(path)
                if not primitives:
                    continue
                lane = MapLane(row["token"], kind, primitives, DEFAULT_LANE_WIDTH)
                if row.get("polygon_token") in self.polygons and lane.length > 0:
                    exterior, _ = self.polygon(row["polygon_token"])
                    width = polygon_area(exterior) / lane.length
                    lane.width = float(np.clip(width, MIN_LANE_WIDTH, MAX_LANE_WIDTH))
                out.append(lane)
        return out

    def drivable_polygons(self) -> list[tuple[np.ndarray, list[np.ndarray]]]:
        return [self.polygon(token) for row in self.data["drivable_area"] for token in row["polygon_tokens"]]

    def layer_polygons(self, layer: str, box=None) -> list[tuple[np.ndarray, list[np.ndarray]]]:
        """Polygons of a polygon layer (drivable_area, lane, lane_connector, ped_crossing, walkway,
        stop_line, carpark_area), optionally only those whose bounds meet box = (xmin, ymin, xmax, ymax)."""
        out = []
        for row in self.data.get(layer, []):
            tokens = row["polygon_tokens"] if "polygon_tokens" in row else [row.get("polygon_token")]
            for token in tokens:
                if token not in self.polygons:
                    continue
                exterior, holes = self.polygon(token)
                if box is None or _meets(exterior, box):
                    out.append((exterior, holes))
        return out

    def layer_lines(self, layer: str, box=None) -> list[np.ndarray]:
        """Polylines of a line layer (lane_divider, road_divider), optionally clipped to box bounds."""
        lines = {row["token"]: row["node_tokens"] for row in self.data["line"]}
        out = []
        for row in self.data.get(layer, []):
            points = np.array([self.nodes[n] for n in lines.get(row["line_token"], [])], dtype=float)
            if len(points) >= 2 and (box is None or _meets(points, box)):
                out.append(points)
        return out


def _meets(points: np.ndarray, box) -> bool:
    xmin, ymin, xmax, ymax = box
    lo, hi = points.min(axis=0), points.max(axis=0)
    return bool(lo[0] <= xmax and hi[0] >= xmin and lo[1] <= ymax and hi[1] >= ymin)
