"""Minimal OpenDRIVE 1.5 files.

`flat_pad` is a placeholder road: one straight, very wide road that covers the scene so every
object stands on a road surface. It carries no lane geometry from the real map.
`map_roads` converts nuScenes map expansion lanes around the scene into OpenDRIVE roads.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from real2sim.nuscenes_map import MapLane
from real2sim.tracks import Scene

SubElement = ET.SubElement


def _lane(parent: ET.Element, lane_id: int, width: float | None) -> None:
    lane = SubElement(parent, "lane", id=str(lane_id), type="driving" if width else "none", level="false")
    SubElement(lane, "link")
    if width:
        SubElement(lane, "width", sOffset="0", a=f"{width:.3f}", b="0", c="0", d="0")


def flat_pad(scene: Scene, margin: float = 50.0) -> ET.ElementTree:
    points = np.vstack([track.xy for track in scene.tracks])
    (xmin, ymin), (xmax, ymax) = points.min(axis=0) - margin, points.max(axis=0) + margin
    length, half_width = xmax - xmin, (ymax - ymin) / 2

    root = ET.Element("OpenDRIVE")
    SubElement(root, "header", revMajor="1", revMinor="5", name=f"flat_pad_{scene.name}", version="1.00")
    road = SubElement(root, "road", name="pad", length=f"{length:.3f}", id="1", junction="-1")
    SubElement(road, "link")
    plan = SubElement(road, "planView")
    geometry = SubElement(
        plan, "geometry", s="0", x=f"{xmin:.3f}", y=f"{(ymin + ymax) / 2:.3f}", hdg="0", length=f"{length:.3f}"
    )
    SubElement(geometry, "line")
    SubElement(road, "elevationProfile")
    SubElement(road, "lateralProfile")
    section = SubElement(SubElement(road, "lanes"), "laneSection", s="0")
    _lane(SubElement(section, "left"), 1, half_width)
    _lane(SubElement(section, "center"), 0, None)
    _lane(SubElement(section, "right"), -1, half_width)

    tree = ET.ElementTree(root)
    ET.indent(tree)
    return tree


def write_flat_pad(scene: Scene, path: str | Path) -> Path:
    path = Path(path)
    flat_pad(scene).write(path, encoding="utf-8", xml_declaration=True)
    return path


def scene_box(scene: Scene, margin: float) -> tuple[float, float, float, float]:
    """Bounding box of all tracks in the global frame, grown by margin."""
    points = np.vstack([track.xy for track in scene.tracks]) + np.asarray(scene.origin)
    (xmin, ymin), (xmax, ymax) = points.min(axis=0) - margin, points.max(axis=0) + margin
    return float(xmin), float(ymin), float(xmax), float(ymax)


def map_roads(scene: Scene, lanes: list[MapLane], name: str) -> ET.ElementTree:
    """One OpenDRIVE road per nuScenes lane or lane connector.

    The road reference line is the lane centreline (shifted into the scene-local frame); a single
    driving lane (-1) of the estimated width is centred on it with laneOffset = width / 2.
    Connections between lanes and junctions are not written: the file serves as road surface and
    lane geometry for replay and display, not for routing.
    """
    ox, oy = scene.origin
    root = ET.Element("OpenDRIVE")
    SubElement(root, "header", revMajor="1", revMinor="5", name=name, version="1.00")
    for road_id, lane in enumerate(lanes, start=1):
        road = SubElement(root, "road", name=lane.token, length=f"{lane.length:.6f}", id=str(road_id),
                          junction="-1")
        SubElement(road, "link")
        plan = SubElement(road, "planView")
        s = 0.0
        for prim in lane.primitives:
            geometry = SubElement(plan, "geometry", s=f"{s:.6f}", x=f"{prim.x - ox:.6f}", y=f"{prim.y - oy:.6f}",
                                  hdg=f"{prim.hdg:.9f}", length=f"{prim.length:.6f}")
            if abs(prim.curvature) < 1e-12:
                SubElement(geometry, "line")
            else:
                SubElement(geometry, "arc", curvature=f"{prim.curvature:.9f}")
            s += prim.length
        SubElement(road, "elevationProfile")
        SubElement(road, "lateralProfile")
        lanes_el = SubElement(road, "lanes")
        SubElement(lanes_el, "laneOffset", s="0", a=f"{lane.width / 2:.3f}", b="0", c="0", d="0")
        section = SubElement(lanes_el, "laneSection", s="0")
        # Lane connectors overlap inside intersections, where real roads carry no lane markings.
        marked = lane.kind == "lane"
        center = SubElement(SubElement(section, "center"), "lane", id="0", type="none", level="false")
        SubElement(center, "link")
        SubElement(center, "roadMark", sOffset="0", type="broken" if marked else "none", weight="standard",
                   color="white", width="0.12")
        right = SubElement(SubElement(section, "right"), "lane", id="-1", type="driving", level="false")
        SubElement(right, "link")
        SubElement(right, "width", sOffset="0", a=f"{lane.width:.3f}", b="0", c="0", d="0")
        SubElement(right, "roadMark", sOffset="0", type="solid" if marked else "none", weight="standard",
                   color="white", width="0.12")
    tree = ET.ElementTree(root)
    ET.indent(tree)
    return tree


def write_map_roads(scene: Scene, lanes: list[MapLane], path: str | Path) -> Path:
    path = Path(path)
    map_roads(scene, lanes, f"nuscenes_{scene.name}").write(path, encoding="utf-8", xml_declaration=True)
    return path
