"""Where scenes come from. Every source offers the same things to the rest of the program:

  scene_names()            list of scene names
  scene(name)              ground-truth Scene (tracks in a local metric frame, time 0 = scene start)
  description(name)        free text, may be empty
  road_lanes(name, gt)     map lanes to build an OpenDRIVE road from, or None
  road_file(name)          a ready-made OpenDRIVE file for the scene, or None
  drivable(name)           drivable-area polygons (global frame) for the on-road check, or None
  map_layers(name, box)    map polygons/lines (global frame) for the viewer, or {}

NuScenesSource  a nuScenes folder (any version, e.g. v1.0-mini or v1.0-trainval), map expansion optional
CsvSource       a tracks CSV in the real2sim format (docs/dinh-dang-csv.md), OpenDRIVE files optional

Source ids name the output folder: results of scene S from source X go to out/X/S/.
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np

from real2sim.nuscenes_io import NuScenesTables
from real2sim.nuscenes_map import MapExpansion, MapLane
from real2sim.tracks import VEHICLE_CATEGORIES, Scene, Track, entity_class, extract_scene
from real2sim.xodr import scene_box

MAP_MARGIN = 30.0  # m of map lanes around a scene's tracks
CSV_COLUMNS = ("scene", "time_s", "object_id", "category", "x_m", "y_m", "yaw_rad", "length_m", "width_m", "height_m")
NUMERIC_COLUMNS = CSV_COLUMNS[4:] + ("time_s",)
MAX_ERRORS = 20

# Short CSV categories -> nuScenes category names (full nuScenes names are accepted as they are).
CSV_CATEGORIES = {
    "car": "vehicle.car", "truck": "vehicle.truck", "bus": "vehicle.bus.rigid", "trailer": "vehicle.trailer",
    "construction": "vehicle.construction", "emergency": "vehicle.emergency.police",
    "motorcycle": "vehicle.motorcycle", "bicycle": "vehicle.bicycle",
    "pedestrian": "human.pedestrian.adult", "animal": "animal",
    "barrier": "movable_object.barrier", "cone": "movable_object.trafficcone", "object": "movable_object.debris",
}


class SourceError(ValueError):
    """A data problem the user can fix; the message is written for them (Vietnamese)."""


def slug(text: str) -> str:
    """Safe name for files, folders and scenario entities: letters, digits, '_', '-', '.'.
    Vietnamese (and other) accents are dropped first: "Ví dụ đường" -> "Vi_du_duong"."""
    text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip()).strip("._")
    return cleaned or "x"


class Source:
    kind = "base"

    def __init__(self, source_id: str, label: str):
        self.id, self.label = slug(source_id), label

    def scene_names(self) -> list[str]:
        raise NotImplementedError

    def scene(self, name: str) -> Scene:
        raise NotImplementedError

    def description(self, name: str) -> str:
        return ""

    def location(self, name: str) -> str | None:
        return None

    def road_lanes(self, name: str, gt: Scene) -> list[MapLane] | None:
        return None

    def road_file(self, name: str) -> Path | None:
        return None

    def drivable(self, name: str):
        return None

    def map_layers(self, name: str, box) -> dict:
        return {}

    def info(self) -> dict:
        return {"id": self.id, "label": self.label, "kind": self.kind, "scenes": len(self.scene_names())}


# ---------------------------------------------------------------------------- nuScenes
class NuScenesSource(Source):
    kind = "nuscenes"

    def __init__(self, dataroot: str | Path, version: str = "v1.0-mini", source_id: str | None = None,
                 label: str | None = None):
        self.dataroot, self.version = Path(dataroot), version
        super().__init__(source_id or f"nuscenes-{version.removeprefix('v1.0-')}", label or f"nuScenes {version}")
        try:
            self.nusc = NuScenesTables(self.dataroot, version)
        except Exception as exc:  # NuScenesError, missing folder, broken JSON
            raise SourceError(f"Không đọc được nuScenes ở {self.dataroot / version}: {exc}") from exc
        self._maps: dict[str, MapExpansion] = {}

    def scene_names(self) -> list[str]:
        return self.nusc.scene_names()

    def scene(self, name: str) -> Scene:
        return extract_scene(self.nusc, name)

    def description(self, name: str) -> str:
        return self.nusc.scene_description(name)

    def location(self, name: str) -> str | None:
        return self.nusc.scene_location(name)

    def map(self, name: str) -> MapExpansion | None:
        location = self.location(name)
        if not location or not (self.dataroot / "maps" / "expansion" / f"{location}.json").is_file():
            return None
        if location not in self._maps:
            self._maps[location] = MapExpansion(self.dataroot, location)
        return self._maps[location]

    def road_lanes(self, name: str, gt: Scene) -> list[MapLane] | None:
        m = self.map(name)
        return m.lanes(*scene_box(gt, MAP_MARGIN)) if m else None

    def drivable(self, name: str):
        m = self.map(name)
        return m.drivable_polygons() if m else None

    def map_layers(self, name: str, box) -> dict:
        m = self.map(name)
        if m is None:
            return {}
        polygons = ("drivable_area", "carpark_area", "walkway", "ped_crossing", "lane", "lane_connector", "stop_line")
        layers = {layer: m.layer_polygons(layer, box) for layer in polygons}
        layers.update({layer: m.layer_lines(layer, box) for layer in ("road_divider", "lane_divider")})
        return layers


# ---------------------------------------------------------------------------- CSV
class CsvSource(Source):
    kind = "csv"

    def __init__(self, path: str | Path, source_id: str | None = None, label: str | None = None):
        path = Path(path)
        self.csv_path = path if path.is_file() else path / "tracks.csv"
        self.folder = self.csv_path.parent
        super().__init__(source_id or self.folder.name, label or self.folder.name)
        if not self.csv_path.is_file():
            raise SourceError(f"Không tìm thấy file {self.csv_path}")
        self.scenes = parse_tracks_csv(self.csv_path.read_text(encoding="utf-8-sig"))

    def scene_names(self) -> list[str]:
        return sorted(self.scenes)

    def scene(self, name: str) -> Scene:
        return self.scenes[name]

    def road_file(self, name: str) -> Path | None:
        path = self.folder / f"{name}.xodr"
        return path if path.is_file() else None


def parse_tracks_csv(text: str) -> dict[str, Scene]:
    """Parse the real2sim tracks CSV; raise SourceError listing every problem found (up to MAX_ERRORS)."""
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in CSV_COLUMNS if c not in header]
    if missing:
        raise SourceError("Thiếu cột: " + ", ".join(missing) + ". Cần đủ các cột: " + ", ".join(CSV_COLUMNS))

    errors: list[str] = []
    rows = defaultdict(lambda: defaultdict(list))  # scene -> object id -> [(t, x, y, yaw, l, w, h, category)]
    for line_no, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        values = {}
        for column in NUMERIC_COLUMNS:
            try:
                values[column] = float(row[column])
                if not math.isfinite(values[column]):
                    raise ValueError
            except ValueError:
                errors.append(f"Dòng {line_no}: cột '{column}' không phải số ({row[column]!r})")
        category = CSV_CATEGORIES.get(row["category"].lower(), row["category"])
        is_ego = row["object_id"].lower() == "ego"  # the ego's category column is not used
        if not is_ego and not known_category(category):
            errors.append(f"Dòng {line_no}: loại vật thể '{row['category']}' không hợp lệ "
                          f"(dùng: {', '.join(CSV_CATEGORIES)})")
        if not row["scene"] or not row["object_id"]:
            errors.append(f"Dòng {line_no}: thiếu 'scene' hoặc 'object_id'")
        if len(errors) >= MAX_ERRORS:
            break
        if errors:
            continue
        if min(values["length_m"], values["width_m"], values["height_m"]) <= 0:
            errors.append(f"Dòng {line_no}: kích thước phải lớn hơn 0")
            continue
        rows[row["scene"]][row["object_id"]].append(
            (values["time_s"], values["x_m"], values["y_m"], values["yaw_rad"],
             values["length_m"], values["width_m"], values["height_m"], category))
    if errors:
        raise SourceError("\n".join(errors[:MAX_ERRORS]))
    if not rows:
        raise SourceError("File không có dòng dữ liệu nào.")

    folders = defaultdict(list)  # results go to out/<source>/<scene>/, and Windows ignores case
    for scene_name in rows:
        folders[slug(scene_name).lower()].append(scene_name)
    clashes = [names for names in folders.values() if len(names) > 1]
    if clashes:
        raise SourceError("Tên cảnh trùng nhau sau khi bỏ dấu và không phân biệt hoa thường: "
                          + "; ".join(" / ".join(f"'{n}'" for n in names) for names in clashes))

    scenes = {}
    for scene_name, objects in rows.items():
        ego_key = next((k for k in objects if k.lower() == "ego"), None)
        if ego_key is None or len(objects[ego_key]) < 2:
            raise SourceError(f"Cảnh '{scene_name}': cần vật thể 'ego' (xe ghi hình) với ít nhất 2 dòng.")
        t0 = min(r[0] for samples in objects.values() for r in samples)
        tracks, used = [], {"ego"}
        for object_id in [ego_key] + sorted(k for k in objects if k != ego_key):
            samples = sorted(objects[object_id])
            times = [s[0] for s in samples]
            if len(set(times)) != len(times):
                raise SourceError(f"Cảnh '{scene_name}', vật thể '{object_id}': có hai dòng cùng thời điểm.")
            arr = np.array([s[:7] for s in samples], dtype=float)
            name = "ego" if object_id == ego_key else _unique(slug(object_id), used)
            category = "vehicle.ego" if object_id == ego_key else samples[0][7]
            length, width, height = np.median(arr[:, 4:7], axis=0)
            tracks.append(Track(name, category, arr[:, 0] - t0, arr[:, 1:3], np.unwrap(arr[:, 3]),
                                (float(length), float(width), float(height)), instance_token=object_id))
        duration = max(float(t.t[-1]) for t in tracks)
        scenes[slug(scene_name)] = Scene(slug(scene_name), (0.0, 0.0), duration, tracks)
    return scenes


def known_category(category: str) -> bool:
    """A nuScenes category this program maps to an OpenSCENARIO entity (tracks.entity_class)."""
    return (category in VEHICLE_CATEGORIES or category == "animal"
            or category.startswith(("human.pedestrian.", "movable_object.", "static_object.")))


def _unique(name: str, used: set[str]) -> str:
    candidate, k = name, 2
    while candidate in used:
        candidate, k = f"{name}_{k}", k + 1
    used.add(candidate)
    return candidate


def write_tracks_csv(scenes: list[Scene], path: str | Path) -> Path:
    """Write scenes in the real2sim CSV format. Positions are box centres in the scene's local
    frame (the ego's rear-axle reference is moved to its box centre)."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for scene in scenes:
            for track in scene.tracks:
                short = "car" if track.name == "ego" else _short_category(track.category)
                length, width, height = track.size
                for t, (x, y), yaw in zip(track.t, track.xy, track.yaw):
                    cx, cy = x + track.bbox_center_x * math.cos(yaw), y + track.bbox_center_x * math.sin(yaw)
                    writer.writerow([scene.name, f"{t:.3f}", track.name, short, f"{cx:.3f}", f"{cy:.3f}",
                                     f"{yaw:.5f}", f"{length:.3f}", f"{width:.3f}", f"{height:.3f}"])
    return path


def _short_category(category: str) -> str:
    for short, full in CSV_CATEGORIES.items():
        if category == full:
            return short
    return "pedestrian" if entity_class(category)[0] == "pedestrian" else category


def load_source(spec: dict) -> Source:
    """Build a source from a registry entry: {"kind": "nuscenes", "dataroot", "version"} or
    {"kind": "csv", "path"}, plus optional "id" and "label"."""
    kind = spec.get("kind")
    if kind == "nuscenes":
        return NuScenesSource(spec["dataroot"], spec.get("version", "v1.0-mini"), spec.get("id"), spec.get("label"))
    if kind == "csv":
        return CsvSource(spec["path"], spec.get("id"), spec.get("label"))
    raise SourceError(f"Loại nguồn không hỗ trợ: {kind!r}")
