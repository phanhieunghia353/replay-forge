"""Tiny synthetic nuScenes-format dataset: one scene, four 2 Hz keyframes."""

import json
import math

import pytest

ORIGIN = (400.0, 1100.0)
T0 = 1_500_000_000_000_000
STEP_US = 500_000


def yaw_quat(yaw):
    return [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]


def build_dataset(root):
    tables = {name: [] for name in (
        "scene", "sample", "sample_data", "ego_pose", "calibrated_sensor", "sensor",
        "sample_annotation", "instance", "category",
    )}
    tables["sensor"] = [{"token": "s_lidar", "channel": "LIDAR_TOP"}, {"token": "s_cam", "channel": "CAM_FRONT"}]
    tables["calibrated_sensor"] = [
        {"token": "cs_lidar", "sensor_token": "s_lidar"},
        {"token": "cs_cam", "sensor_token": "s_cam"},
    ]
    tables["category"] = [
        {"token": "c_car", "name": "vehicle.car"},
        {"token": "c_ped", "name": "human.pedestrian.adult"},
        {"token": "c_bar", "name": "movable_object.barrier"},
    ]
    tables["instance"] = [
        {"token": "i_car", "category_token": "c_car"},
        {"token": "i_ped", "category_token": "c_ped"},
        {"token": "i_bar", "category_token": "c_bar"},
    ]
    tables["scene"] = [{"token": "sc1", "name": "scene-0001"}]
    for k in range(4):
        ts = T0 + k * STEP_US
        tables["sample"].append({"token": f"smp{k}", "scene_token": "sc1", "timestamp": ts})
        tables["ego_pose"].append({
            "token": f"ep{k}", "timestamp": ts,
            "translation": [ORIGIN[0] + 5.0 * 0.5 * k, ORIGIN[1], 0.0], "rotation": yaw_quat(0.0),
        })
        tables["sample_data"].append({
            "token": f"sd{k}", "sample_token": f"smp{k}", "ego_pose_token": f"ep{k}",
            "calibrated_sensor_token": "cs_lidar", "timestamp": ts, "is_key_frame": True,
        })
        tables["sample_data"].append({
            "token": f"sdc{k}", "sample_token": f"smp{k}", "ego_pose_token": f"ep{k}",
            "calibrated_sensor_token": "cs_cam", "timestamp": ts, "is_key_frame": True,
        })
        # car drives north at 10 m/s, heading +90 deg
        tables["sample_annotation"].append({
            "token": f"a_car{k}", "sample_token": f"smp{k}", "instance_token": "i_car",
            "translation": [ORIGIN[0] + 20.0, ORIGIN[1] - 10.0 + 10.0 * 0.5 * k, 1.0],
            "size": [1.9, 4.5, 1.6], "rotation": yaw_quat(math.pi / 2),
        })
        # barrier: identical box every keyframe
        tables["sample_annotation"].append({
            "token": f"a_bar{k}", "sample_token": f"smp{k}", "instance_token": "i_bar",
            "translation": [ORIGIN[0] + 5.0, ORIGIN[1] + 3.0, 0.5],
            "size": [0.5, 2.0, 1.0], "rotation": yaw_quat(0.0),
        })
    # pedestrian seen only in the last two keyframes
    for k in (2, 3):
        tables["sample_annotation"].append({
            "token": f"a_ped{k}", "sample_token": f"smp{k}", "instance_token": "i_ped",
            "translation": [ORIGIN[0] + 10.0 + 0.7 * (k - 2), ORIGIN[1] + 6.0, 0.9],
            "size": [0.6, 0.7, 1.8], "rotation": yaw_quat(0.0),
        })
    base = root / "v1.0-mini"
    base.mkdir(parents=True)
    for name, rows in tables.items():
        (base / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    return root


@pytest.fixture
def dataroot(tmp_path):
    return build_dataset(tmp_path / "nuscenes")
