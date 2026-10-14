import math

import numpy as np
import pytest

from real2sim.nuscenes_io import NuScenesError, NuScenesTables
from real2sim.tracks import EGO_SIZE, Scene, entity_class, extract_scene, quaternion_yaw


def test_quaternion_yaw():
    for yaw in (0.0, 0.5, -2.0, math.pi / 2):
        assert quaternion_yaw([math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]) == pytest.approx(yaw)


def test_entity_class():
    assert entity_class("vehicle.car") == ("vehicle", "car")
    assert entity_class("vehicle.bus.rigid") == ("vehicle", "bus")
    assert entity_class("human.pedestrian.child") == ("pedestrian", "pedestrian")
    assert entity_class("movable_object.barrier") == ("misc", "barrier")
    assert entity_class("movable_object.trafficcone") == ("misc", "obstacle")


def test_extract_scene(dataroot):
    scene = extract_scene(NuScenesTables(dataroot), "scene-0001")
    names = [track.name for track in scene.tracks]
    assert names == ["ego", "barrier_001", "car_001", "pedestrian_001"]
    assert scene.origin == (400.0, 1100.0)
    assert scene.duration == pytest.approx(1.5)

    ego, barrier, car, ped = scene.tracks
    assert ego.size == EGO_SIZE
    np.testing.assert_allclose(ego.xy[:, 0], [0, 2.5, 5.0, 7.5])
    np.testing.assert_allclose(car.t, [0, 0.5, 1.0, 1.5])
    np.testing.assert_allclose(car.xy[0], [20.0, -10.0])
    np.testing.assert_allclose(car.yaw, math.pi / 2)
    assert car.size == (4.5, 1.9, 1.6)  # nuScenes size is [w, l, h]
    assert not car.is_static
    assert barrier.is_static
    np.testing.assert_allclose(ped.t, [1.0, 1.5])


def test_stationary_allowance_grows_with_length():
    from real2sim.tracks import Track

    xy = np.array([[0.0, 0.0], [0.0, 2.4]])  # 1.2 m from the mean
    truck = Track("truck_001", "vehicle.truck", np.array([0.0, 1.0]), xy, np.zeros(2), (6.0, 2.3, 2.6))
    car = Track("car_001", "vehicle.car", np.array([0.0, 1.0]), xy, np.zeros(2), (4.0, 1.8, 1.5))
    assert truck.is_stationary  # allowance 0.25 * 6 m = 1.5 m
    assert not car.is_stationary  # allowance 1.0 m


def test_scene_roundtrip(dataroot, tmp_path):
    scene = extract_scene(NuScenesTables(dataroot), "scene-0001")
    scene.save(tmp_path / "s.json")
    loaded = Scene.load(tmp_path / "s.json")
    assert [t.name for t in loaded.tracks] == [t.name for t in scene.tracks]
    np.testing.assert_allclose(loaded.tracks[2].xy, scene.tracks[2].xy)


def test_unknown_scene(dataroot):
    with pytest.raises(NuScenesError):
        NuScenesTables(dataroot).samples("scene-9999")
