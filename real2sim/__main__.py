"""Command line: python -m real2sim [--csv PATH | --dataroot DIR --version V] <command> ...

The data source is nuScenes by default (data/nuscenes, v1.0-mini) or a tracks CSV with --csv.
Results go to <out>/<source id>/<scene>/, e.g. out/nuscenes-mini/scene-0061/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from real2sim import report
from real2sim.abstraction import METHODS
from real2sim.esmini import find_esmini
from real2sim.holdout import holdout_scene
from real2sim.pipeline import PipelineError, events_scene, replay_scene, variants_scene
from real2sim.sources import CsvSource, NuScenesSource, Source, SourceError, write_tracks_csv

ESMINI_MISSING = "esmini not found (use --esmini PATH, set ESMINI_BIN, or unzip it into tools/esmini-demo/)"


def make_source(args) -> Source:
    return CsvSource(args.csv) if args.csv else NuScenesSource(args.dataroot, args.version)


def check_scene(source: Source, name: str) -> None:
    if name not in source.scene_names():
        raise SourceError(f"Unknown scene {name!r}; available: {', '.join(source.scene_names()[:10])} …")


def cmd_scenes(args) -> int:
    for name in make_source(args).scene_names():
        print(name)
    return 0


def cmd_replay(args) -> int:
    """Write one scenario per method, replay each in esmini, compare with the raw keyframe labels."""
    source = make_source(args)
    check_scene(source, args.scene)
    exe = find_esmini(args.esmini)
    replay_scene(source, args.scene, args.out, exe, args.method, args.road, args.dt, log=print)
    if exe is None:
        print(f"{ESMINI_MISSING}; scenarios written, replay skipped.")
        return 2
    return 0


def cmd_variants(args) -> int:
    """Speed/offset variants of every moving vehicle, replayed in esmini; validity and rarity counts."""
    source = make_source(args)
    check_scene(source, args.scene)
    exe = find_esmini(args.esmini)
    if exe is None:
        print(ESMINI_MISSING)
        return 2
    variants_scene(source, args.scene, args.out, exe, args.method, args.road, args.dt, args.jobs,
                   args.max_targets, args.keep, log=print)
    return 0


def cmd_events(args) -> int:
    """Stage 1: a vehicle ahead brakes or stops; baseline = nobody reacts, pilot = human-like reactions."""
    source = make_source(args)
    check_scene(source, args.scene)
    exe = find_esmini(args.esmini)
    if exe is None:
        print(ESMINI_MISSING)
        return 2
    events_scene(source, args.scene, args.out, exe, args.method, args.road, args.dt, args.jobs, args.keep, log=print,
                 reaction=args.reaction)
    return 0


def cmd_holdout(args) -> int:
    """Held-out check of metric 1 (real2sim/holdout.py): writes <out>/<source>/<scene>/holdout.json."""
    source = make_source(args)
    names = args.scene or source.scene_names()
    for name in names:
        check_scene(source, name)
        result = holdout_scene(source.scene(name))
        folder = Path(args.out) / source.id / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "holdout.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"{name}: {result['tracks']} moving tracks, ADE on hidden keyframes "
              + ", ".join(f"{m} {v:.3f} m" for m, v in result["summary"].items() if v is not None))
    return 0


def cmd_report(args) -> int:
    """Aggregate both metrics over all scenes of the source (and its sensitivity runs) into summary.md/json."""
    source_id = make_source(args).id
    folder = Path(args.out) / source_id
    sens_root = Path(args.out) / "sensitivity"
    sensitivity = {f"{p.name.lstrip('r')} s": p / source_id for p in sorted(sens_root.iterdir())
                   if (p / source_id).is_dir()} if sens_root.is_dir() else {}
    data = report.collect(folder, sensitivity) if folder.is_dir() else {"scenes": []}
    if not data["scenes"]:
        print(f"no scene outputs under {folder}")
        return 1
    text = report.to_markdown(data)
    (folder / "summary.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    (folder / "summary.md").write_text(text, encoding="utf-8")
    try:
        print(text)
    except UnicodeEncodeError:  # a console without Vietnamese characters (cp1252): the files are written anyway
        print(f"written {folder / 'summary.md'} and summary.json")
    return 0


def cmd_export_csv(args) -> int:
    """Write scenes of the source in the real2sim CSV format (an example of the import format)."""
    source = make_source(args)
    names = args.scene or source.scene_names()
    for name in names:
        check_scene(source, name)
    path = write_tracks_csv([source.scene(name) for name in names], args.to)
    print(f"{len(names)} scene(s) -> {path}")
    return 0


def cmd_app(args) -> int:
    """Serve the web app on the local machine and open it in the browser."""
    import webbrowser

    from real2sim.app.api import Workspace
    from real2sim.app.server import serve

    httpd = serve(Workspace(args.data, args.out), args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    print(f"real2sim app running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="real2sim")
    parser.add_argument("--dataroot", default="data/nuscenes", help="nuScenes root (folder containing v1.0-mini/)")
    parser.add_argument("--version", default="v1.0-mini", help="nuScenes version folder, e.g. v1.0-trainval")
    parser.add_argument("--csv", help="use a tracks CSV (file or folder with tracks.csv) instead of nuScenes")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scenes", help="list scene names").set_defaults(func=cmd_scenes)

    replay = sub.add_parser("replay", help="write scenarios, replay in esmini, measure replay error")
    replay.add_argument("--scene", required=True)
    replay.add_argument("--method", nargs="+", choices=METHODS, default=list(METHODS))
    replay.add_argument("--out", default="out")
    replay.add_argument("--road", choices=("map", "flat", "none"), default="map",
                        help="map: the source's .xodr or nuScenes map lanes (falls back to none)")
    replay.add_argument("--esmini", help="path to esmini executable")
    replay.add_argument("--dt", type=float, default=0.05)
    replay.set_defaults(func=cmd_replay)

    var = sub.add_parser("variants", help="generate speed/offset variants, replay, count valid and rare ones")
    var.add_argument("--scene", required=True)
    var.add_argument("--method", nargs="+", choices=("baseline", "pilot"), default=["baseline", "pilot"])
    var.add_argument("--out", default="out")
    var.add_argument("--esmini", help="path to esmini executable")
    var.add_argument("--dt", type=float, default=0.05)
    var.add_argument("--jobs", type=int, default=4, help="parallel esmini runs")
    var.add_argument("--max-targets", type=int, default=0, help="limit target vehicles (0 = all)")
    var.add_argument("--road", choices=("map", "flat", "none"), default="map",
                     help="road network written next to the kept scenarios")
    var.add_argument("--keep", choices=("rare", "valid", "none"), default="rare",
                     help="which variants get a full-scene .xosc written (and replayed in full); "
                          "rare = valuable under criteria v2 (close or hard braking)")
    var.set_defaults(func=cmd_variants)

    ev = sub.add_parser("events", help="stage 1: lead-vehicle braking events, without and with human reactions")
    ev.add_argument("--scene", required=True)
    ev.add_argument("--method", nargs="+", choices=("baseline", "pilot"), default=["baseline", "pilot"])
    ev.add_argument("--out", default="out")
    ev.add_argument("--esmini", help="path to esmini executable")
    ev.add_argument("--dt", type=float, default=0.05)
    ev.add_argument("--jobs", type=int, default=4, help="parallel worker processes")
    ev.add_argument("--road", choices=("map", "flat", "none"), default="map")
    ev.add_argument("--reaction", type=float, default=None,
                    help="drivers' reaction time in s (default 1.0; other values for sensitivity runs)")
    ev.add_argument("--keep", choices=("rare", "valid", "none"), default="rare",
                    help="which valid variants keep their .xosc (rare = valuable for the ego)")
    ev.set_defaults(func=cmd_events)

    hold = sub.add_parser("holdout", help="metric 1 held-out check: hide every other label, measure on the hidden ones")
    hold.add_argument("--scene", nargs="*", help="scenes (default: all of the source)")
    hold.add_argument("--out", default="out")
    hold.set_defaults(func=cmd_holdout)

    rep = sub.add_parser("report", help="aggregate replay and variant results of all scenes of the source")
    rep.add_argument("--out", default="out")
    rep.set_defaults(func=cmd_report)

    exp = sub.add_parser("export-csv", help="write scenes as a real2sim tracks CSV")
    exp.add_argument("--scene", nargs="*", help="scene names (default: all)")
    exp.add_argument("--to", required=True, help="output CSV file")
    exp.set_defaults(func=cmd_export_csv)

    app = sub.add_parser("app", help="open the local web app")
    app.add_argument("--data", default="data", help="folder holding datasets and the source list")
    app.add_argument("--out", default="out", help="folder for results")
    app.add_argument("--host", default="127.0.0.1")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    app.set_defaults(func=cmd_app)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SourceError, PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
