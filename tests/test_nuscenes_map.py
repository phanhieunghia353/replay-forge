import json
import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from real2sim.nuscenes_io import NuScenesTables
from real2sim.nuscenes_map import MapExpansion, advance, arcline_primitives
from real2sim.safety import box_track
from real2sim.tracks import Scene, extract_scene
from real2sim.variants import on_road_fraction, points_in_ring
from real2sim.xodr import map_roads, scene_box

R = 10.0


def quarter_turn():
    """Straight 5 m east, then a left quarter circle of radius R: one LSL element (0-length first L)."""
    return [{"start_pose": [100.0, 200.0, 0.0], "end_pose": [105.0 + R, 200.0 + R, math.pi / 2],
             "shape": "LSL", "radius": R, "segment_length": [0.0, 5.0, math.pi / 2 * R]}]


def write_map(root):
    nodes, polygons = [], []

    def ring(token, pts):
        ids = []
        for i, (x, y) in enumerate(pts):
            nodes.append({"token": f"{token}_n{i}", "x": x, "y": y})
            ids.append(f"{token}_n{i}")
        polygons.append({"token": token, "exterior_node_tokens": ids, "holes": []})

    # lane polygon 3.5 m wide around the straight part only (area / length is checked loosely)
    ring("p_lane", [(100, 198.25), (105 + R, 198.25), (105 + R, 201.75), (100, 201.75)])
    ring("p_drive", [(90, 190), (130, 190), (130, 230), (90, 230)])
    data = {
        "node": nodes, "polygon": polygons,
        "lane": [{"token": "lane_1", "polygon_token": "p_lane"}],
        "lane_connector": [{"token": "far_away", "polygon_token": ""}],
        "arcline_path_3": {"lane_1": quarter_turn(), "far_away": [
            {"start_pose": [5000.0, 5000.0, 0.0], "end_pose": [5010.0, 5000.0, 0.0], "shape": "LSL",
             "radius": 50.0, "segment_length": [0.0, 10.0, 0.0]}]},
        "drivable_area": [{"token": "d1", "polygon_tokens": ["p_drive"]}],
    }
    path = root / "maps" / "expansion"
    path.mkdir(parents=True)
    (path / "test-town.json").write_text(json.dumps(data), encoding="utf-8")


def test_advance_and_primitives():
    x, y, h = advance(0, 0, 0, math.pi / 2 * R, 1 / R)  # quarter left turn
    assert (x, y, h) == pytest.approx((R, R, math.pi / 2))
    prims = arcline_primitives(quarter_turn())
    assert [p.curvature for p in prims] == [0.0, pytest.approx(1 / R)]  # zero-length L dropped
    end = advance(prims[-1].x, prims[-1].y, prims[-1].hdg, prims[-1].length, prims[-1].curvature)
    assert end == pytest.approx((105 + R, 200 + R, math.pi / 2))


def test_lanes_in_region_and_xodr(tmp_path):
    write_map(tmp_path)
    m = MapExpansion(tmp_path, "test-town")
    lanes = m.lanes(90, 190, 130, 230)
    assert [lane.token for lane in lanes] == ["lane_1"]
    assert 2.5 <= lanes[0].width <= 5.0

    scene = Scene("s", (100.0, 200.0), 1.0, [])
    root = map_roads(scene, lanes, "test").getroot()
    road = root.find("road")
    geometries = road.findall("planView/geometry")
    assert [g[0].tag for g in geometries] == ["line", "arc"]
    assert float(geometries[0].get("x")) == pytest.approx(0.0)  # shifted into the scene frame
    assert float(geometries[1].get("s")) == pytest.approx(5.0)
    assert float(road.get("length")) == pytest.approx(5.0 + math.pi / 2 * R, abs=1e-5)
    width = float(road.find("lanes/laneSection/right/lane/width").get("a"))
    assert float(road.find("lanes/laneOffset").get("a")) == pytest.approx(width / 2, abs=1e-3)
    assert road.find("lanes/laneSection/right/lane/roadMark").get("type") == "solid"

    lanes[0].kind = "lane_connector"  # inside intersections: no markings
    road = map_roads(scene, lanes, "test").getroot().find("road")
    assert {m.get("type") for m in road.iter("roadMark")} == {"none"}


def test_points_in_ring_and_on_road(tmp_path):
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    inside = points_in_ring(np.array([[5, 5], [15, 5], [0.5, 9.5], [-1, -1]], float), square)
    assert inside.tolist() == [True, False, True, False]

    write_map(tmp_path)
    polygons = MapExpansion(tmp_path, "test-town").drivable_polygons()
    t = np.arange(0, 4.01, 0.1)
    xy = np.column_stack([-5 + 10 * t, np.zeros_like(t)])  # scene frame, origin (100, 200): x 95..135
    box = box_track(t, xy, np.zeros_like(t), 4, 2)
    assert on_road_fraction(box, polygons, (100.0, 200.0)) == pytest.approx(36 / 41, abs=0.03)


def test_scene_location_without_log(dataroot):
    nusc = NuScenesTables(dataroot)
    assert nusc.scene_location("scene-0001") is None
    gt = extract_scene(nusc, "scene-0001")
    xmin, ymin, xmax, ymax = scene_box(gt, 10.0)
    assert xmin < 400 < xmax and ymin < 1100 < ymax  # global frame
