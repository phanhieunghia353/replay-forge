import json

import pytest

from real2sim.report import collect, to_markdown


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def variant_summary(valid, rare):
    return {"targets": 2, "generated": 10, "written": 8, "valid": valid, "rare": rare, "rare_near_miss": 1,
            "rare_targets": 1, "rare_events": 1, "new_rare_events": 1, "recorded_rare_events": 0}


def run_block(commit):
    return {"code": {"commit": commit, "dirty": False}, "esmini": {"version": "v3.9.0"},
            "config": {"methods": ["baseline", "pilot"], "dt": 0.05}}


def test_collect_and_markdown(tmp_path):
    for scene, ades in (("scene-0001", (0.0, 1.0, 0.1)), ("scene-0002", (0.0, 3.0, 0.3))):
        (tmp_path / scene).mkdir()
        (tmp_path / scene / "tracks_gt.json").write_text("{}", encoding="utf-8")
        for method, ade in zip(("exact", "baseline", "pilot"), ades):
            write(tmp_path / scene / method / "metrics.json", {
                "summary": {"moving": {"tracks": 1, "ade": ade}},
                "per_track": {"car_001": {"static": False, "ade": ade}, "barrier_001": {"static": True, "ade": 9.0}},
            })
        commit = "aaaa" if scene == "scene-0001" else "bbbb"
        for method, (valid, rare) in (("baseline", (4, 1)), ("pilot", (6, 2))):
            write(tmp_path / scene / "variants" / method / "report.json",
                  {"summary": variant_summary(valid, rare), "run": run_block(commit)})

    data = collect(tmp_path)
    assert data["scenes"] == ["scene-0001", "scene-0002"]
    assert data["replay_overall"]["baseline"]["ade"] == pytest.approx(2.0)  # static tracks excluded
    assert data["variant_totals"]["pilot"]["valid"] == 12
    assert data["variant_totals"]["pilot"]["valid_rate"] == pytest.approx(12 / 16)
    text = to_markdown(data)
    assert "| scene-0002 | 1 | 0.000 | 3.000 | 0.300 |" in text
    assert "**12/16 (75.0%)**" in text
    assert data["variant_totals"]["pilot"]["rare_events"] == 2
    # results of two code versions in one table are flagged (audit 2.6)
    assert "Cảnh báo:** kết quả phụ lục, cách cũ đến từ 2 lượt chạy" in text
    assert "chỉ số 1: không rõ" in text  # metrics.json without a run block


def v2_summary(new_events):
    groups = {"far": 5, "close": 1, "mild": 2, "hard": 1, "unavoidable": 1, "late": 0}
    return {**variant_summary(10, 3), "valuable": 2, "valuable_events": 2, "new_valuable_events": new_events,
            "recorded_valuable_events": 0, "rejected_geometry": 1, "rejected_dynamics": 2,
            "groups": groups, "group_events": {g: min(v, 1) for g, v in groups.items()},
            "unavoidable_reasons": {"no_decel": 1}, "new_valuable_by_type": {"vehicle/front": new_events},
            "sensitivity": [{"threshold": "reaction_s", "value": 1.0, "base": True, "new_valuable_events": new_events},
                            {"threshold": "reaction_s", "value": 2.5, "base": False, "new_valuable_events": 0}]}


def test_markdown_v2(tmp_path):
    for scene in ("scene-0001", "scene-0002"):
        for method in ("baseline", "pilot"):
            write(tmp_path / scene / "variants" / method / "report.json", {"summary": v2_summary(2)})
    data = collect(tmp_path)
    total = data["variant_totals"]["pilot"]
    assert total["new_valuable_events"] == 4 and total["groups"]["hard"] == 2
    assert {(i["value"], i["new_valuable_events"]) for i in total["sensitivity"]} == {(1.0, 4), (2.5, 0)}
    text = to_markdown(data)
    assert "| phải phanh gấp | 2 (2) | 2 (2) |" in text
    assert "| thời gian phản xạ (s) | **1** | 4 | 4 |" in text
    assert "2 / 2 / **2**" in text  # files / events / new events per scene


def test_scene_found_from_variants_alone_and_old_counts(tmp_path):
    write(tmp_path / "scene-0003" / "variants" / "pilot" / "report.json",
          {"summary": {k: v for k, v in variant_summary(1, 0).items() if k != "rare_events"}})
    data = collect(tmp_path)
    assert data["scenes"] == ["scene-0003"]  # no tracks_gt.json (audit 2.5)
    assert data["variant_totals"]["pilot"]["rare_events"] is None  # unknown, not 0


def event_summary(attempted, valid, valuable, rejected):
    return {"attempted": attempted, "valid": valid, "valid_rate": valid / attempted, "encounters": 4,
            "encounters_with_valid": 3, "valuable": valuable, "valuable_encounters": min(valuable, 2),
            "groups": {"hard": 0, "close": valuable, "mild": 1, "far": valid - valuable - 1, "collision": 0},
            "rejected_by": rejected, "strong_braking_events": 0, "kept_xosc": valuable, "esmini_failed": 0}


def test_metric2_events_holdout_and_sensitivity(tmp_path):
    out = tmp_path / "src"
    for scene in ("scene-0001", "scene-0002"):
        write(out / scene / "events" / "baseline" / "report.json",
              {"summary": event_summary(10, 3, 0, {"collision": 7}), "run": run_block("cccc")})
        write(out / scene / "events" / "pilot" / "report.json",
              {"summary": event_summary(10, 8, 2, {"label_error": 2}), "run": run_block("cccc")})
        write(out / scene / "holdout.json", {"tracks": 1, "summary": {"exact": 0.1, "baseline": 2.0, "pilot": 0.2},
                                             "per_track": {"car_001": {m: {"ade": v} for m, v in
                                                                       (("exact", 0.1), ("baseline", 2.0), ("pilot", 0.2))}}})
        write(tmp_path / "sens" / scene / "events" / "pilot" / "report.json",
              {"summary": event_summary(10, 5, 4, {"collision": 5})})
        write(tmp_path / "sens" / scene / "events" / "baseline" / "report.json",
              {"summary": event_summary(10, 3, 0, {"collision": 7})})
    data = collect(out, {"1.5 s": tmp_path / "sens"})
    assert data["event_totals"]["pilot"]["valid"] == 16 and data["event_totals"]["baseline"]["rejected_by"] == {"collision": 14}
    assert data["holdout_overall"]["pilot"]["ade"] == pytest.approx(0.2)
    assert data["sensitivity"]["1.5 s"]["pilot"]["valid"] == 10
    text = to_markdown(data)
    assert "**6/20 (30.0%)** | **16/20 (80.0%)**" in text
    assert "| **tất cả** | 2 | **0.100** | **2.000** | **0.200** |" in text
    assert "| 1.5 s | 6/20 (30.0%) | 10/20 (50.0%) | 0 | 8 |" in text
    assert "| nhãn gốc lỗi | 0 | 4 |" in text
    assert "Phụ lục" not in text  # no older variant results in this folder
