import numpy as np
import pytest

from real2sim.nuscenes_io import NuScenesTables
from real2sim.pipeline import replay_scene
from real2sim.sources import CsvSource, NuScenesSource, SourceError, parse_tracks_csv, slug, write_tracks_csv
from real2sim.tracks import extract_scene

HEADER = "scene,time_s,object_id,category,x_m,y_m,yaw_rad,length_m,width_m,height_m\n"


def test_nuscenes_source(dataroot):
    source = NuScenesSource(dataroot)
    assert source.id == "nuscenes-mini" and source.scene_names() == ["scene-0001"]
    assert [t.name for t in source.scene("scene-0001").tracks] == ["ego", "barrier_001", "car_001", "pedestrian_001"]
    assert source.road_lanes("scene-0001", source.scene("scene-0001")) is None  # no map in the test data
    with pytest.raises(SourceError):
        NuScenesSource(dataroot, "v1.0-nope")


def test_csv_roundtrip(dataroot, tmp_path):
    scene = extract_scene(NuScenesTables(dataroot), "scene-0001")
    write_tracks_csv([scene], tmp_path / "tracks.csv")
    source = CsvSource(tmp_path)
    assert source.kind == "csv" and source.scene_names() == ["scene-0001"]
    back = source.scene("scene-0001")
    assert [t.name for t in back.tracks] == [t.name for t in scene.tracks]
    car = next(t for t in back.tracks if t.name == "car_001")
    np.testing.assert_allclose(car.xy, scene.tracks[2].xy, atol=1e-3)
    assert car.category == "vehicle.car" and car.size == pytest.approx((4.5, 1.9, 1.6))
    ego = back.tracks[0]
    assert ego.bbox_center_x == 0.0  # CSV positions are box centres
    np.testing.assert_allclose(ego.xy[:, 0], scene.tracks[0].xy[:, 0] + 1.39, atol=1e-3)
    assert back.tracks[3].t.tolist() == [1.0, 1.5]  # times kept relative to the scene start


def test_csv_pipeline_writes_scenarios(tmp_path):
    text = HEADER + "".join(
        f"demo,{t},ego,car,{5 * t},0,0,4.5,1.9,1.6\n" for t in (0, 0.5, 1, 1.5, 2)) + "demo,0,cone 1,cone,10,3,0,0.4,0.4,0.7\n"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tracks.csv").write_text(text, encoding="utf-8")
    (tmp_path / "data" / "demo.xodr").write_text("<OpenDRIVE/>", encoding="utf-8")
    source = CsvSource(tmp_path / "data", label="Demo")
    assert [t.name for t in source.scene("demo").tracks] == ["ego", "cone_1"]
    assert replay_scene(source, "demo", tmp_path / "out", None) == {}  # no esmini: scenarios only
    folder = tmp_path / "out" / "data" / "demo"
    assert (folder / "pilot" / "demo.xosc").is_file()
    assert (folder / "pilot" / "demo.xodr").read_text(encoding="utf-8") == "<OpenDRIVE/>"  # the source's own road


@pytest.mark.parametrize("text, message", [
    ("scene,time_s\nx,1\n", "Thiếu cột"),
    (HEADER + "a,0,ego,car,abc,0,0,4,2,1.5\n", "không phải số"),
    (HEADER + "a,0,car1,spaceship,0,0,0,4,2,1.5\n", "không hợp lệ"),
    (HEADER + "a,0,car1,car,0,0,0,4,2,1.5\n", "'ego'"),
    (HEADER + "a,0,ego,car,0,0,0,4,2,1.5\na,0,ego,car,1,0,0,4,2,1.5\n", "cùng thời điểm"),
    (HEADER + "a,0,ego,car,0,0,0,0,2,1.5\n", "lớn hơn 0"),
    (HEADER, "không có dòng"),
    (HEADER + "a,0,car1,spaceship.fake,0,0,0,4,2,1.5\n", "không hợp lệ"),  # audit 2.8
    (HEADER + "".join(f"{s},{t},ego,car,{t},0,0,4,2,1.5\n" for s in ("Đường A", "duong a") for t in (0, 1)),
     "trùng nhau"),  # audit 2.8: same results folder on Windows
])
def test_csv_errors_are_readable(text, message):
    with pytest.raises(SourceError) as err:
        parse_tracks_csv(text)
    assert message in str(err.value)


def test_csv_ego_wheelbase(tmp_path):
    """Audit 2.9: only the nuScenes ego (Renault Zoe) gets the Zoe wheelbase."""
    import xml.etree.ElementTree as ET

    from real2sim.xosc import write_xosc
    scene = parse_tracks_csv(HEADER + "".join(f"a,{t},ego,car,{t},0,0,10,2.5,3\n" for t in (0, 1)))["a"]
    root = ET.parse(write_xosc(scene, tmp_path / "a.xosc")).getroot()
    front = root.find("Entities/ScenarioObject[@name='ego']/Vehicle/Axles/FrontAxle")
    assert float(front.get("positionX")) == pytest.approx(6.0)  # 0.6 x 10 m, not 2.588 m


def test_slug():
    assert slug("scene 0061/../x") == "scene_0061_.._x" and slug("  ") == "x"
    assert slug("Ví dụ đường Đông") == "Vi_du_duong_Dong"
