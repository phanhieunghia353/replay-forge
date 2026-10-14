import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from real2sim.app.api import Workspace
from real2sim.app.jobs import JobRunner
from real2sim.app.server import clean, serve
from real2sim.sources import SourceError

HEADER = "scene,time_s,object_id,category,x_m,y_m,yaw_rad,length_m,width_m,height_m\n"
CSV = HEADER + "".join(f"demo,{t},ego,car,{5 * t},0,0,4.5,1.9,1.6\n" for t in (0, 0.5, 1, 1.5, 2))


@pytest.fixture
def workspace(dataroot, tmp_path):
    ws = Workspace(tmp_path / "data", tmp_path / "out")
    ws.add_nuscenes(str(dataroot), "v1.0-mini")
    return ws


def test_sources_and_scene(workspace):
    assert [s["id"] for s in workspace.sources()] == ["nuscenes-mini"]
    rows = workspace.scene_list("nuscenes-mini")
    assert [r["name"] for r in rows] == ["scene-0001"] and rows[0]["processed"] is False

    scene = workspace.scene("nuscenes-mini", "scene-0001")
    assert scene["map"] == {} and scene["source"] == "nuscenes-mini"
    names = [t["name"] for t in scene["tracks"]]
    assert names == ["ego", "barrier_001", "car_001", "pedestrian_001"]
    car = scene["tracks"][2]
    assert set(car) >= {"gt", "baseline", "pilot", "size", "kind", "stationary", "errors"}
    assert car["gt"]["x"][0] == pytest.approx(20.0) and car["gt"]["t"] == [0.0, 0.5, 1.0, 1.5]
    assert workspace.scene("nuscenes-mini", "scene-0001") is scene  # cached


def test_add_csv_source(workspace, tmp_path):
    entry = workspace.add_csv("Công ty A", CSV, {"demo.xodr": "<OpenDRIVE/>"})
    assert entry["kind"] == "csv"
    folder = Path(entry["path"])
    assert (folder / "tracks.csv").is_file() and (folder / "demo.xodr").is_file()
    assert [r["name"] for r in workspace.scene_list(entry["id"])] == ["demo"]
    assert json.loads((tmp_path / "data" / "sources.json").read_text(encoding="utf-8"))[1]["id"] == entry["id"]
    workspace.remove_source(entry["id"])
    assert [s["id"] for s in workspace.sources()] == ["nuscenes-mini"]
    # audit 2.7: the same name again gets a new id, so it neither overwrites the removed source's
    # imported files nor picks up its old results
    (tmp_path / "out" / "cong_ty_a-2").mkdir(parents=True)
    again = workspace.add_csv("Công ty A", CSV)
    assert again["id"] not in (entry["id"], "cong_ty_a-2") and again["id"].startswith("cong_ty_a")


def test_process_runs_jobs(workspace, monkeypatch):
    monkeypatch.setattr("real2sim.app.api.find_esmini", lambda explicit=None: Path("esmini.exe"))
    calls = []

    def fake_process(source, scene, out_root, exe, log, progress):
        calls.append((source.id, scene))
        progress(0.5, "halfway")
        log("done")

    monkeypatch.setattr("real2sim.app.api.process_scene", fake_process)
    jobs = workspace.process("nuscenes-mini")
    assert [j["scene"] for j in jobs] == ["scene-0001"]
    assert workspace.runner.wait_idle(10)
    assert calls == [("nuscenes-mini", "scene-0001")]
    assert workspace.jobs()[0]["status"] == "done" and workspace.jobs()[0]["log"] == ["done"]


def test_variants_list_and_one_variant(workspace, tmp_path):
    """The side panel lists every valid stage-1 variant; one variant comes with the trajectories of every
    vehicle it changes: the braking lead, and in the pilot the ego reacting behind it."""
    times = [0.5 * k for k in range(25)]  # 12 s, the ego follows the lead at 5 m/s, 20 m apart
    text = HEADER + "".join(f"long,{t},ego,car,{5 * t},0,0,4.5,1.9,1.6\n" for t in times) \
        + "".join(f"long,{t},lead,car,{20 + 5 * t},0,0,4.5,1.9,1.6\n" for t in times)
    source = workspace.add_csv("Dài", text)["id"]
    row = {"id": "lead_t02.0_stop_d0_a4", "encounter": "lead@2s_stop", "actor": "lead", "t0": 2.0, "decel": 4.0,
           "target": "stop", "dwell": 0.0, "valid": True, "reasons": [], "group": "mild", "reacted": ["ego", "lead"],
           "kept": False, "max_decel_used": {"lead": 4.0, "ego": 2.1},
           "ego": {"a_used": 2.1, "a_min": 1.5, "min_gap": 3.0, "min_ttc": 2.5, "recorded_min_gap": 15.5}}
    rejected = {**row, "id": "lead_t02.0_stop_d0_a8", "decel": 8.0, "valid": False, "reasons": ["collision"],
                "group": None}
    for method in ("pilot", "baseline"):
        folder = tmp_path / "out" / source / "long" / "events" / method
        folder.mkdir(parents=True)
        summary = {"attempted": 2, "valid": 1, "rejected_by": {"collision": 1}, "valuable": 0, "valuable_encounters": 0}
        (folder / "report.json").write_text(json.dumps({"summary": summary, "variants": [row, rejected]}),
                                            encoding="utf-8")

    row0 = workspace.scene_list(source)[0]
    assert row0["valid"] == 1 and row0["written"] == 2 and row0["processed"] is False  # metric 1 not run
    cases = workspace.scene(source, "long")["variants"]["pilot"]["cases"]
    assert [c["id"] for c in cases] == ["lead_t02.0_stop_d0_a4"] and cases[0]["a_used"] == 2.1

    pilot = workspace.variant(source, "long", "pilot", "lead_t02.0_stop_d0_a4")
    assert pilot["changed"]["lead"]["role"] == "event" and pilot["changed"]["ego"]["role"] == "reacted"
    lead, ego = pilot["changed"]["lead"]["poses"], pilot["changed"]["ego"]["poses"]
    assert lead["x"][-1] < 20 + 5 * 12 - 5  # it stopped, then drove on: behind its recording
    assert lead["t"] == ego["t"] and min(l - e for l, e in zip(lead["x"], ego["x"])) > 4.5  # the ego never hits it
    baseline = workspace.variant(source, "long", "baseline", "lead_t02.0_stop_d0_a4")
    assert list(baseline["changed"]) == ["lead"]  # nobody reacts
    with pytest.raises(SourceError):
        workspace.variant(source, "long", "pilot", "nope")


def test_job_failure_is_reported():
    def boom(job, log, progress):
        raise RuntimeError("esmini crashed")

    runner = JobRunner(boom)
    runner.submit("s", "scene-1")
    assert runner.wait_idle(10)
    job = runner.list()[0]
    assert job["status"] == "failed" and "esmini crashed" in job["error"]


def test_clean_makes_json_safe():
    assert clean({"a": float("inf"), "b": [1, float("nan")], "c": (True, "x")}) == {"a": None, "b": [1, None], "c": [True, "x"]}


@pytest.fixture
def server(workspace):
    httpd = serve(workspace, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.headers.get("Content-Type"), response.read()


def post(url, data):
    request = urllib.request.Request(url, json.dumps(data).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_http_routes(server):
    status, kind, body = get(server + "/")
    assert status == 200 and kind.startswith("text/html") and b"real2sim" in body
    assert b'type="importmap"' in body  # three.js is resolved through the import map
    for path in ("/static/js/main.js", "/static/js/viewer3d.js", "/static/vendor/three.module.min.js",
                 "/static/vendor/OrbitControls.js"):
        status, kind, _ = get(server + path)
        assert status == 200 and kind.startswith("text/javascript"), path
    assert json.loads(get(server + "/api/sources")[2])[0]["id"] == "nuscenes-mini"
    assert json.loads(get(server + "/api/scenes?source=nuscenes-mini")[2])[0]["name"] == "scene-0001"
    assert len(json.loads(get(server + "/api/scene?source=nuscenes-mini&name=scene-0001")[2])["tracks"]) == 4
    assert "esmini" in json.loads(get(server + "/api/status")[2])
    assert json.loads(get(server + "/api/jobs")[2]) == []


def test_http_add_csv(server):
    entry = post(server + "/api/sources", {"kind": "csv", "label": "Demo", "csv_text": CSV})
    assert json.loads(get(server + f"/api/scenes?source={entry['id']}")[2])[0]["name"] == "demo"
    with pytest.raises(urllib.error.HTTPError) as err:
        post(server + "/api/sources", {"kind": "csv", "label": "Bad", "csv_text": "a,b\n1,2\n"})
    assert err.value.code == 400 and "Thiếu cột" in json.loads(err.value.read())["error"]


def test_http_process_without_esmini(server, monkeypatch):
    monkeypatch.setattr("real2sim.app.api.find_esmini", lambda explicit=None: None)
    with pytest.raises(urllib.error.HTTPError) as err:
        post(server + "/api/process", {"source": "nuscenes-mini"})
    assert err.value.code == 400 and "esmini" in json.loads(err.value.read())["error"]


@pytest.mark.parametrize("path", ["/api/scene?source=nuscenes-mini&name=nope", "/api/scenes?source=nope",
                                  "/static/../server.py", "/static/%2e%2e/server.py", "/nothing"])
def test_http_errors(server, path):
    with pytest.raises(urllib.error.HTTPError) as err:
        get(server + path)
    assert err.value.code in (400, 404)


def _follow_scene(workspace):
    times = [0.5 * k for k in range(25)]  # 12 s, the ego follows the lead at 5 m/s, 20 m apart
    text = HEADER + "".join(f"long,{t},ego,car,{5 * t},0,0,4.5,1.9,1.6\n" for t in times) \
        + "".join(f"long,{t},lead,car,{20 + 5 * t},0,0,4.5,1.9,1.6\n" for t in times) \
        + "".join(f"long,{t},bus,bus,{-40 + 5 * t},40,0,12,2.6,3.2\n" for t in times)
    return workspace.add_csv("Theo sau", text)["id"]


def test_simulate_a_user_made_scenario(workspace):
    source = _follow_scene(workspace)
    scene = workspace.scene(source, "long")
    assert "lead" in scene["selectable"] and scene["drivers"]["bus"]["max_decel"] == 5.0
    out = workspace.simulate_event(source, "long", {"actor": "lead", "t0": 2, "decel": 4, "target": "stop",
                                                    "dwell": 1})
    assert set(out["changed"]) == {"lead", "ego"} and out["changed"]["ego"]["role"] == "reacted"
    modes = [m[2] for m in out["changed"]["ego"]["modes"]]
    assert modes[:3] == ["nominal", "waiting", "driving"]  # follows the recording, reacts, then drives itself
    assert any(m[2] == "lead" for m in out["changed"]["ego"]["leaders"])
    kinds = [m["kind"] for m in out["markers"]]
    assert "brake_start" in kinds and "reacts" in kinds and "closest" in kinds
    assert out["result"]["valid"] and len(out["series"]["ego"]["gap"]) == len(out["t"])
    slower = workspace.simulate_event(source, "long", {"actor": "lead", "t0": 2, "decel": 4, "target": "stop",
                                                       "dwell": 1, "reaction": 2.0})
    react = lambda o: next(m["t"] for m in o["markers"] if m["kind"] == "reacts")  # noqa: E731
    assert react(slower) == pytest.approx(react(out) + 1.0, abs=0.06)


@pytest.mark.parametrize("params, words", [
    ({"actor": "nope", "t0": 2, "decel": 4}, "Không có xe"),
    ({"actor": "lead", "t0": 2, "decel": 9}, "Mức phanh"),
    ({"actor": "bus", "t0": 2, "decel": 6}, "xe buýt"),
    ({"actor": "lead", "t0": 30, "decel": 4}, "không có trong dữ liệu"),
])
def test_simulate_explains_bad_requests(workspace, params, words):
    source = _follow_scene(workspace)
    with pytest.raises(SourceError, match=words):
        workspace.simulate_event(source, "long", params)


def test_export_and_download(workspace, monkeypatch):
    source = _follow_scene(workspace)
    monkeypatch.setattr("real2sim.app.api.find_esmini", lambda explicit=None: Path("esmini.exe"))

    def fake_export(source, name, event, exe, folder, react, reaction, model=None):
        folder.mkdir(parents=True)
        (folder / "report.json").write_text("{}", encoding="utf-8")
        return {"valid": True}

    monkeypatch.setattr("real2sim.app.api.export_event", fake_export)
    out = workspace.export_event(source, "long", {"actor": "lead", "t0": 2, "decel": 4, "target": "half"})
    assert out["id"] == "lead_t02.0_half_a4" and out["download"].endswith("id=lead_t02.0_half_a4")
    assert workspace.download(source, "long", out["id"]).suffix == ".zip"
    with pytest.raises(SourceError):
        workspace.download(source, "long", "../secret")


def test_rare_package(workspace, tmp_path):
    source = _follow_scene(workspace)
    with pytest.raises(SourceError, match="chưa có ca hiếm"):
        workspace.download(source, "long", "rare")
    folder = tmp_path / "out" / source / "long" / "events" / "pilot" / "xosc"
    folder.mkdir(parents=True)
    (folder / "lead_t02.0_stop_d0_a8.xosc").write_text("<OpenSCENARIO/>", encoding="utf-8")
    assert workspace.download(source, "long", "rare").name == "long_ca_hiem.zip"
