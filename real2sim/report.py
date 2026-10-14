"""Aggregate the two metrics of several scenes into one report (summary.md / summary.json).

  metric 1  replay error of the reconstructions (replay), and the held-out check (holdout.json)
  metric 2  stage-1 events (events/<method>/report.json): valid scenarios generated, baseline = nobody
            reacts, pilot = human-like reactions; plus sensitivity runs with other reaction times
  appendix  the older variant generator (variants/), kept for comparison only

Each result carries a "run" block (pipeline.run_info); the report lists the distinct runs it mixes,
so a table built from results of different code versions or settings is visible as such.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

METHODS = ("exact", "baseline", "pilot")
VARIANT_METHODS = ("baseline", "pilot")
COUNTS = ("targets", "generated", "written", "valid", "rare", "rare_near_miss", "rare_targets", "rare_events",
          "new_rare_events", "recorded_rare_events", "valuable", "valuable_events", "new_valuable_events",
          "recorded_valuable_events", "rejected_geometry", "rejected_dynamics")
GROUPS = ("far", "close", "mild", "hard", "unavoidable", "late")
GROUP_LABELS = {"far": "xa", "close": "sát", "mild": "phanh nhẹ là đủ", "hard": "phải phanh gấp",
                "unavoidable": "không tránh được bằng phanh", "late": "xuất hiện quá muộn"}
EVENT_COUNTS = ("attempted", "valid", "encounters", "encounters_with_valid", "valuable", "valuable_encounters")
EVENT_GROUPS = ("hard", "close", "mild", "far", "collision")
EVENT_GROUP_LABELS = {"hard": "phải phanh gấp", "close": "suýt chạm", "mild": "phanh nhẹ là đủ", "far": "không ảnh hưởng",
                      "collision": "xe ghi hình đâm (không ai phản ứng)"}
REASON_LABELS = {"collision": "các xe khác đâm nhau", "label_error": "nhãn gốc lỗi", "physics": "sai vật lý",
                 "tailgating": "bám sát phi lý", "unsupported_interaction": "nhập làn, cắt ngang, người đi bộ (chưa mô phỏng)",
                 "unsupported_appearing": "xe vừa vào khung hình đúng chỗ tình huống (chưa mô phỏng)",
                 "esmini": "esmini lỗi"}
THRESHOLD_LABELS = {"reaction_s": "thời gian phản xạ (s)", "detect_ttc_s": "TTC phát hiện (s)",
                    "comfort_decel": "phanh nhẹ tối đa (m/s²)", "max_decel": "phanh gấp tối đa (m/s²)",
                    "close_ttc_s": "sát: TTC (s)", "close_gap_m": "sát: khoảng cách (m)",
                    "min_presence_s": "có mặt trước xung đột (s)"}


def _run_key(kind: str, run: dict | None) -> str:
    if not run:
        return f"{kind}: không rõ (kết quả cũ, chưa ghi lượt chạy)"
    config = {k: v for k, v in run["config"].items() if k != "method"}
    code = run["code"]["commit"] or "không rõ"
    dirty = " + sửa chưa commit" if run["code"].get("dirty") else ""
    return (f"{kind}: code {code[:10]}{dirty}, esmini {run['esmini'].get('version') or 'không rõ'}, "
            f"cấu hình {json.dumps(config, sort_keys=True, ensure_ascii=False)}")


def collect_events(out: Path, scenes: list[str] | None = None) -> dict:
    """Stage-1 event summaries per method and scene, their totals, and the runs they come from."""
    if scenes is None:
        scenes = sorted(p.name for p in out.iterdir() if (p / "events").is_dir()) if out.is_dir() else []
    per = {m: {} for m in VARIANT_METHODS}
    runs: dict[str, list[str]] = {}
    for scene in scenes:
        for method in VARIANT_METHODS:
            path = out / scene / "events" / method / "report.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                per[method][scene] = data["summary"]
                if data["summary"]["attempted"]:  # a scene with no variant never runs esmini: nothing to compare
                    runs.setdefault(_run_key("chỉ số 2", data.get("run")), []).append(f"{scene}/{method}")
    totals = {}
    for method, rows in per.items():
        total = {key: sum(r[key] for r in rows.values()) for key in EVENT_COUNTS}
        total["valid_rate"] = total["valid"] / total["attempted"] if total["attempted"] else 0.0
        total["groups"] = {g: sum(r["groups"].get(g, 0) for r in rows.values()) for g in EVENT_GROUPS}
        total["rejected_by"] = {}
        for r in rows.values():
            for k, v in r["rejected_by"].items():
                total["rejected_by"][k] = total["rejected_by"].get(k, 0) + v
        totals[method] = total
    return {"per_scene": per, "totals": totals, "runs": runs}


def collect(out: Path, sensitivity: dict[str, Path] | None = None) -> dict:
    """out: one source's result folder. sensitivity: label -> the same source's results of a sensitivity run."""
    scenes = sorted(p.name for p in out.iterdir()
                    if p.is_dir() and ((p / "tracks_gt.json").is_file() or (p / "variants").is_dir()
                                       or (p / "events").is_dir()))
    replay = {m: {} for m in METHODS}
    moving_ade = {m: [] for m in METHODS}
    variants = {m: {} for m in VARIANT_METHODS}
    runs: dict[str, list[str]] = {}
    for scene in scenes:
        for method in METHODS:
            path = out / scene / method / "metrics.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                replay[method][scene] = data["summary"].get("moving")
                moving_ade[method] += [row["ade"] for row in data["per_track"].values() if not row["static"]]
                runs.setdefault(_run_key("chỉ số 1", data.get("run")), []).append(f"{scene}/{method}")
        for method in VARIANT_METHODS:
            path = out / scene / "variants" / method / "report.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                variants[method][scene] = data["summary"]
                runs.setdefault(_run_key("phụ lục, cách cũ", data.get("run")), []).append(f"{scene}/{method}")
    totals = {}
    for method, per_scene in variants.items():
        # a count missing from an older report makes its total unknown rather than too small
        total = {key: (sum(s[key] for s in per_scene.values()) if all(key in s for s in per_scene.values()) else None)
                 for key in COUNTS}
        total["valid_rate"] = total["valid"] / total["written"] if total["written"] else 0.0
        v2 = [s for s in per_scene.values() if "groups" in s]
        if per_scene and len(v2) == len(per_scene):
            for key in ("groups", "group_events", "unavoidable_reasons", "new_valuable_by_type"):
                total[key] = {}
                for s in v2:
                    for k, v in s[key].items():
                        total[key][k] = total[key].get(k, 0) + v
            sens = {}
            for s in v2:
                for item in s["sensitivity"]:
                    k = (item["threshold"], item["value"])
                    sens[k] = {**item, "new_valuable_events": sens.get(k, {}).get("new_valuable_events", 0)
                               + item["new_valuable_events"]}
            total["sensitivity"] = list(sens.values())
        totals[method] = total
    overall = {m: {"tracks": len(v), "ade": float(np.mean(v)) if v else None} for m, v in moving_ade.items()}
    holdout, held = {}, {m: [] for m in METHODS}
    for scene in scenes:
        path = out / scene / "holdout.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            holdout[scene] = data
            for row in data["per_track"].values():
                for m in METHODS:
                    held[m].append(row[m]["ade"])
    holdout_overall = {m: {"tracks": len(v), "ade": float(np.mean(v)) if v else None} for m, v in held.items()}
    peaks = {m: [v for h in holdout.values() for v in h.get("smoothness", {}).get(m, {}).values()] for m in METHODS}
    holdout_overall["smoothness"] = {m: {"tracks": len(v), "median_peak": float(np.median(v)) if v else None,
                                         "over_limit": float(np.mean(np.array(v) > 4.0)) if v else None}
                                     for m, v in peaks.items()}
    ev = collect_events(out, scenes)
    for key, items in ev["runs"].items():
        runs.setdefault(key, []).extend(items)
    sens = {label: collect_events(folder)["totals"] for label, folder in (sensitivity or {}).items()}
    return {"scenes": scenes, "replay_moving": replay, "replay_overall": overall, "holdout": holdout,
            "holdout_overall": holdout_overall, "events": ev["per_scene"], "event_totals": ev["totals"],
            "sensitivity": sens, "variants": variants, "variant_totals": totals, "runs": runs}


def _cell(value, fmt="{:.3f}"):
    return "-" if value is None else fmt.format(value)


def to_markdown(data: dict) -> str:
    lines = ["## Chỉ số 1: ADE nhóm chuyển động (m), so với nhãn gốc", "",
             "| scene | số vật thể | exact | baseline | pilot |", "|---|---|---|---|---|"]
    for scene in data["scenes"]:
        rows = [data["replay_moving"][m].get(scene) for m in METHODS]
        tracks = next((r["tracks"] for r in rows if r), 0)
        lines.append(f"| {scene} | {tracks} | " + " | ".join(_cell(r and r["ade"]) for r in rows) + " |")
    overall = data["replay_overall"]
    lines.append(f"| **tất cả (trung bình theo vật thể)** | {overall['pilot']['tracks']} | "
                 + " | ".join(f"**{_cell(overall[m]['ade'])}**" for m in METHODS) + " |")
    if data.get("holdout"):
        held = data["holdout_overall"]
        lines += ["", "### Kiểm chéo: sai số trên các mốc nhãn bị giấu (m)", "",
                  "Giấu một nửa số mốc nhãn (mốc thứ 2, 4, 6…), dựng lại từ nửa còn lại, đo trên nửa bị giấu. "
                  "exact ở đây = nối thẳng giữa các nhãn còn lại.", "",
                  "| scene | số vật thể | nối thẳng (exact) | baseline | pilot |", "|---|---|---|---|---|"]
        for scene, h in data["holdout"].items():
            lines.append(f"| {scene} | {h['tracks']} | " + " | ".join(_cell(h["summary"][m]) for m in METHODS) + " |")
        lines.append(f"| **tất cả** | {held['pilot']['tracks']} | "
                     + " | ".join(f"**{_cell(held[m]['ade'])}**" for m in METHODS) + " |")
        sm = held.get("smoothness", {})
        if sm.get("pilot", {}).get("tracks"):
            lines += ["", "Độ êm của quỹ đạo dựng từ toàn bộ nhãn: gia tốc lớn nhất (phân vị 99, lấy mẫu 0,05 s) của từng vật thể chuyển động.", "",
                      "| | nối thẳng (exact) | baseline | pilot |", "|---|---|---|---|",
                      "| trung vị (m/s²) | " + " | ".join(_cell(sm[m]["median_peak"], "{:.2f}") for m in METHODS) + " |",
                      "| tỷ lệ vật thể vượt 4 m/s² | " + " | ".join(_cell(sm[m]["over_limit"] and 100 * sm[m]["over_limit"], "{:.0f}%") for m in METHODS) + " |"]
    lines += _events_markdown(data)
    if not any(data["variants"][m] for m in VARIANT_METHODS):
        return _runs_markdown(data, lines)
    lines += ["", "## Phụ lục: cách sinh biến thể cũ (chỉ để so sánh)", "",
              "Dời thời gian và đổi tốc độ cả quỹ đạo của một vật thể, không ai phản ứng. Đã thay bằng chỉ số 2 ở trên "
              "vì biến thể trông giả (docs/thiet-ke-kich-ban-hanh-vi.md).", "",
              "Hiếm có giá trị (tiêu chí phiên bản 2: sát + phải phanh gấp): số file / số sự kiện khác nhau / "
              "số sự kiện không có trong bản ghi thật. Tiêu chí cũ (TTC < 1,5 s hoặc cách < 1 m): số file / số sự kiện.",
              "", "| scene | diễn viên | baseline hợp lệ | pilot hợp lệ | hiếm có giá trị baseline | hiếm có giá trị pilot "
              "| trong bản ghi | tiêu chí cũ baseline | tiêu chí cũ pilot |",
              "|---|---|---|---|---|---|---|---|---|"]

    def ratio(s):
        return f"{s['valid']}/{s['written']} ({100 * s['valid'] / s['written']:.1f}%)" if s["written"] else "0/0"

    def n(value):
        return _cell(value, "{}")

    def valuable(s):
        return f"{n(s.get('valuable'))} / {n(s.get('valuable_events'))} / **{n(s.get('new_valuable_events'))}**"

    def old(s):
        return f"{s['rare']} / {n(s.get('rare_events'))}"

    for scene in data["scenes"]:
        b, p = data["variants"]["baseline"].get(scene), data["variants"]["pilot"].get(scene)
        if not (b and p):
            continue
        lines.append(f"| {scene} | {p['targets']} | {ratio(b)} | {ratio(p)} | {valuable(b)} | {valuable(p)} | "
                     f"{n(p.get('recorded_valuable_events'))} | {old(b)} | {old(p)} |")
    tb, tp = data["variant_totals"]["baseline"], data["variant_totals"]["pilot"]
    lines.append(f"| **tổng** | {tp['targets']} | **{ratio(tb)}** | **{ratio(tp)}** | {valuable(tb)} | {valuable(tp)} | "
                 f"{n(tp['recorded_valuable_events'])} | {old(tb)} | {old(tp)} |")
    lines.append(f"\nLý do loại: hình học (chồng hộp với vật khác) baseline {n(tb['rejected_geometry'])}, "
                 f"pilot {n(tp['rejected_geometry'])}; động lực học (vượt tốc độ hoặc gia tốc) baseline "
                 f"{n(tb['rejected_dynamics'])}, pilot {n(tp['rejected_dynamics'])}.")

    if "groups" in tb and "groups" in tp:
        lines += ["", "### Các nhóm (tiêu chí phiên bản 2): số file (số sự kiện)", "",
                  "| nhóm | baseline | pilot |", "|---|---|---|"]
        for g in GROUPS:
            lines.append(f"| {GROUP_LABELS[g]} | {tb['groups'][g]} ({tb['group_events'][g]}) | "
                         f"{tp['groups'][g]} ({tp['group_events'][g]}) |")
        lines.append(f"\nKhông tránh được bằng phanh, theo lý do: baseline {tb['unavoidable_reasons']}, "
                     f"pilot {tp['unavoidable_reasons']}. Sự kiện hiếm có giá trị mới, theo kiểu (pilot): "
                     f"{tp['new_valuable_by_type']}.")
        lines += ["", "### Độ nhạy: số sự kiện hiếm có giá trị mới khi đổi từng ngưỡng (in đậm: ngưỡng đã chọn)", "",
                  "| ngưỡng | giá trị | baseline | pilot |", "|---|---|---|---|"]
        base_rows = {(i["threshold"], i["value"]): i for i in tb["sensitivity"]}
        for item in tp["sensitivity"]:
            value = f"**{item['value']:g}**" if item["base"] else f"{item['value']:g}"
            other = base_rows.get((item["threshold"], item["value"]), {}).get("new_valuable_events")
            lines.append(f"| {THRESHOLD_LABELS.get(item['threshold'], item['threshold'])} | {value} | {n(other)} | "
                         f"{item['new_valuable_events']} |")

    return _runs_markdown(data, lines)


def _events_markdown(data: dict) -> list[str]:
    totals = data.get("event_totals") or {}
    if not totals or not totals.get("pilot", {}).get("attempted"):
        return []

    def ratio(s):
        return f"{s['valid']}/{s['attempted']} ({100 * s['valid'] / s['attempted']:.1f}%)" if s["attempted"] else "0/0"

    lines = ["", "## Chỉ số 2: số kịch bản hợp lệ sinh được", "",
             "Mỗi biến thể: một xe đang có xe khác chạy sau phanh (2, 4, 6, 8 m/s²) tới dừng, dừng 3 s, hoặc xuống nửa tốc độ, "
             "mỗi 2 s. **baseline**: không ai phản ứng; **pilot**: các xe phía sau, kể cả xe ghi hình, phản ứng như người lái "
             "(phản xạ 1 s). Cùng danh sách biến thể, cùng bộ kiểm hợp lệ. “Lần phanh” = một xe phanh ở một thời điểm "
             "(gộp các mức phanh và đích của nó). Hiếm = xe ghi hình suýt chạm hoặc phải phanh gấp.", "",
             "| scene | biến thể | baseline hợp lệ | pilot hợp lệ | lần phanh có biến thể hợp lệ (baseline / pilot) "
             "| hiếm baseline | hiếm pilot |", "|---|---|---|---|---|---|---|"]
    per = data["events"]
    for scene in data["scenes"]:
        b, p = per["baseline"].get(scene), per["pilot"].get(scene)
        if not (b and p):
            continue
        lines.append(f"| {scene} | {p['attempted']} | {ratio(b)} | {ratio(p)} | {b['encounters_with_valid']} / "
                     f"{p['encounters_with_valid']} (trong {p['encounters']}) | {b['valuable']} ({b['valuable_encounters']} lần) "
                     f"| {p['valuable']} ({p['valuable_encounters']} lần) |")
    tb, tp = totals["baseline"], totals["pilot"]
    lines.append(f"| **tổng** | {tp['attempted']} | **{ratio(tb)}** | **{ratio(tp)}** | {tb['encounters_with_valid']} / "
                 f"{tp['encounters_with_valid']} (trong {tp['encounters']}) | **{tb['valuable']}** ({tb['valuable_encounters']} lần) "
                 f"| **{tp['valuable']}** ({tp['valuable_encounters']} lần) |")
    lines += ["", "### Lý do bị loại (một biến thể có thể có nhiều lý do)", "", "| lý do | baseline | pilot |", "|---|---|---|"]
    for reason in sorted(set(tb["rejected_by"]) | set(tp["rejected_by"]), key=lambda r: -tp["rejected_by"].get(r, 0)):
        lines.append(f"| {REASON_LABELS.get(reason, reason)} | {tb['rejected_by'].get(reason, 0)} | {tp['rejected_by'].get(reason, 0)} |")
    lines += ["", "### Biến thể hợp lệ theo việc xe ghi hình phải làm", "", "| nhóm | baseline | pilot |", "|---|---|---|"]
    for g in EVENT_GROUPS:
        lines.append(f"| {EVENT_GROUP_LABELS[g]} | {tb['groups'][g]} | {tp['groups'][g]} |")
    if data.get("sensitivity"):
        lines += ["", "### Độ nhạy: đổi thời gian phản xạ của người lái", "",
                  "| phản xạ | baseline hợp lệ | pilot hợp lệ | hiếm baseline | hiếm pilot |", "|---|---|---|---|---|"]
        rows = [("1.0 (đã chọn)", totals)] + sorted(data["sensitivity"].items())
        for label, t in rows:
            b, p = t["baseline"], t["pilot"]
            lines.append(f"| {label} | {ratio(b)} | {ratio(p)} | {b['valuable']} | {p['valuable']} |")
    return lines


def _runs_markdown(data: dict, lines: list[str]) -> str:
    runs = data.get("runs", {})
    lines += ["", "## Lượt chạy", ""]
    for kind in ("chỉ số 1", "chỉ số 2", "phụ lục, cách cũ"):
        keys = [k for k in runs if k.startswith(kind)]
        if len(keys) > 1:
            lines.append(f"**Cảnh báo:** kết quả {kind} đến từ {len(keys)} lượt chạy khác nhau (code, esmini hoặc cấu hình).")
    for key, items in runs.items():
        lines.append(f"- {key}: {len(items)} kết quả")
    return "\n".join(lines) + "\n"
