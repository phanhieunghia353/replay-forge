import xml.etree.ElementTree as ET

import pytest

from real2sim.nuscenes_io import NuScenesTables
from real2sim.tracks import extract_scene
from real2sim.xodr import write_flat_pad
from real2sim.xosc import write_xosc


@pytest.fixture
def scene(dataroot):
    return extract_scene(NuScenesTables(dataroot), "scene-0001")


def test_xosc_structure(scene, tmp_path):
    root = ET.parse(write_xosc(scene, tmp_path / "s.xosc", date="2026-10-09T00:00:00")).getroot()
    assert root.find("FileHeader").get("revMinor") == "1"
    assert root.find("RoadNetwork/LogicFile") is None
    objects = root.findall("Entities/ScenarioObject")
    assert [o.get("name") for o in objects] == ["ego", "barrier_001", "car_001", "pedestrian_001"]
    assert root.find("Entities/ScenarioObject[@name='car_001']/Vehicle").get("vehicleCategory") == "car"
    assert root.find("Entities/ScenarioObject[@name='pedestrian_001']/Pedestrian") is not None
    assert root.find("Entities/ScenarioObject[@name='barrier_001']/MiscObject").get("miscObjectCategory") == "barrier"
    assert len(root.findall("Storyboard/Init/Actions/Private")) == 4

    groups = root.findall("Storyboard/Story/Act/ManeuverGroup")
    assert [g.get("name") for g in groups][0] == "presence"
    assert [g.find("Actors/EntityRef").get("entityRef") for g in groups[1:]] == ["ego", "car_001", "pedestrian_001"]


def test_presence(scene, tmp_path):
    """The pedestrian has data from 1.0 s to the scene end (1.5 s): removed in Init, added at 0.9 s."""
    root = ET.parse(write_xosc(scene, tmp_path / "s.xosc")).getroot()
    removed = root.findall("Storyboard/Init/Actions/GlobalAction/EntityAction")
    assert [a.get("entityRef") for a in removed] == ["pedestrian_001"]
    assert removed[0].find("DeleteEntityAction") is not None
    init = [child.tag for child in root.find("Storyboard/Init/Actions")]
    assert init.index("Private") > init.index("GlobalAction")  # schema order
    events = root.findall(".//ManeuverGroup[@name='presence']//Event")
    assert [e.get("name") for e in events] == ["appear_pedestrian_001"]
    at = events[0].find("StartTrigger//SimulationTimeCondition")
    assert float(at.get("value")) == pytest.approx(0.9)
    added = events[0].find(".//AddEntityAction/Position/WorldPosition")
    assert float(added.get("x")) == pytest.approx(10.0) and float(added.get("y")) == pytest.approx(6.0)

    # a track ending before the scene does is removed 0.1 s after its last sample
    car = next(t for t in scene.tracks if t.name == "car_001")
    car.t, car.xy, car.yaw = car.t[:2], car.xy[:2], car.yaw[:2]
    root = ET.parse(write_xosc(scene, tmp_path / "s2.xosc")).getroot()
    vanish = root.find(".//Event[@name='vanish_car_001']")
    assert float(vanish.find("StartTrigger//SimulationTimeCondition").get("value")) == pytest.approx(0.6)
    assert vanish.find(".//EntityAction[@entityRef='car_001']/DeleteEntityAction") is not None
    assert root.find(".//Event[@name='appear_car_001']") is None  # present from the start


def test_rear_axle_on_reference_point(scene, tmp_path):
    root = ET.parse(write_xosc(scene, tmp_path / "s.xosc")).getroot()
    for name, centre_x in (("ego", 1.39), ("car_001", 0.0)):
        vehicle = root.find(f"Entities/ScenarioObject[@name='{name}']/Vehicle")
        assert float(vehicle.find("Axles/RearAxle").get("positionX")) == 0.0
        assert float(vehicle.find("Axles/FrontAxle").get("positionX")) > 0.0
        assert float(vehicle.find("BoundingBox/Center").get("x")) == pytest.approx(centre_x)


def test_trajectory_timing(scene, tmp_path):
    root = ET.parse(write_xosc(scene, tmp_path / "s.xosc")).getroot()
    event = root.find(".//ManeuverGroup[@name='group_pedestrian_001']//Event")
    vertices = event.findall(".//Polyline/Vertex")
    assert [float(v.get("time")) for v in vertices] == [1.0, 1.5]  # absolute simulation time
    start = event.find("StartTrigger//SimulationTimeCondition")
    assert float(start.get("value")) == 1.0 and start.get("rule") == "greaterOrEqual"
    assert event.find(".//Timing").get("domainAbsoluteRelative") == "absolute"
    assert event.find(".//TrajectoryFollowingMode").get("followingMode") == "position"
    first = vertices[0].find("Position/WorldPosition")
    assert float(first.get("x")) == pytest.approx(10.0) and float(first.get("y")) == pytest.approx(6.0)


def test_flat_pad(scene, tmp_path):
    xodr = write_flat_pad(scene, tmp_path / "pad.xodr")
    root = ET.parse(write_xosc(scene, tmp_path / "s.xosc", xodr.name)).getroot()
    assert root.find("RoadNetwork/LogicFile").get("filepath") == "pad.xodr"
    road = ET.parse(xodr).getroot().find("road")
    geometry = road.find("planView/geometry")
    x0, y0, length = (float(geometry.get(k)) for k in ("x", "y", "length"))
    width = float(road.find("lanes/laneSection/left/lane/width").get("a"))
    for track in scene.tracks:
        assert (track.xy[:, 0] >= x0).all() and (track.xy[:, 0] <= x0 + length).all()
        assert (abs(track.xy[:, 1] - y0) <= width).all()
