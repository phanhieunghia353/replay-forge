# replay-forge

> Recorded drives in. Replayable OpenSCENARIO out. Then the car in front slams the brakes.

English · [Tiếng Việt](README.vi.md)

`replay-forge` takes annotated object trajectories (nuScenes, or your own CSV), rebuilds the scene as an
OpenSCENARIO 1.1 scenario on an OpenDRIVE road generated from the map, replays it in
[esmini](https://github.com/esmini/esmini), and measures how far the replay drifts from the labels.

Then it forges variants the way real near misses happen: a vehicle that someone is following brakes,
and everyone behind it, the ego included, reacts like a human driver (1 s reaction, enhanced IDM,
per-driver headway fitted from the log). Every variant goes through the same validity checks; anything
physically or behaviourally implausible is rejected **with a reason**, never shipped.

Built for task N3-09B (AI20K, team P-056): *convert annotated object trajectories into OpenSCENARIO,
generate speed and gap variants to create rare situations.* The Python package is still called
`real2sim`.

```
 nuScenes JSON + map expansion            your CSV (+ .xodr)
          \                                   /
           +-------------- Source -----------+
                             |
                   tracks (scene-local frame)
                             |
          reconstruct: exact | baseline | pilot          real2sim/abstraction.py
                             |
          OpenSCENARIO 1.1 + OpenDRIVE (from lanes)      real2sim/xosc.py, xodr.py
                             |
                esmini replay -> metric 1                real2sim/esmini.py, metrics.py
                             |
   lead brakes -> followers react (IDM, 1 s) -> checks   real2sim/behavior.py, events.py
                             |
             metric 2 + rare cases + .xosc export        real2sim/pipeline.py, report.py
```

## Numbers

10 nuScenes-mini scenes, esmini v3.9.0. Every figure below comes from one run per metric, reproducible
with the commands further down; the full tables live in `out/nuscenes-mini/summary.md` after a run and
in [docs/gia-dinh-va-chi-so.md](docs/gia-dinh-va-chi-so.md) (sections 7 and 8).

**Metric 1: replay error** (mean distance to the labels over moving objects: 335 tracks; 321 have enough labels for the held-out column)

| reconstruction | on the labels it was built from | on held-out labels (every other one hidden) |
|---|---|---|
| exact (point by point) | 0.000 m | 0.091 m (straight lines between the kept labels) |
| baseline (one constant speed) | 1.771 m | 1.983 m |
| **pilot** (smoothed path, speed knots every 2 s) | **0.098 m** | **0.133 m** |

Straight lines between labels fit positions slightly better than the pilot, but the labels are noisy:
81 % of tracks then accelerate or brake harder than 4 m/s² at some point, against 16 % for the pilot.
The pilot trades about 4 cm for motion that is physically possible.

**Metric 2: valid scenarios generated** (777 variants: every 2 s, braking at 2/4/6/8 m/s², to a stop,
a 3 s stop, or half speed)

| | baseline: nobody reacts | **pilot: followers react** |
|---|---|---|
| valid variants | 225 (29.0 %) | **591 (76.1 %)** |
| braking moments with a valid variant | 69 / 174 | **146 / 174** |
| other vehicles crashing into each other | 488 | 33 |
| near misses for the ego | 4 | 18 (6 braking moments) |

Sensitivity to the drivers' reaction time:

| reaction | pilot valid | ego near misses |
|---|---|---|
| 0.7 s | 78.1 % | 0 |
| **1.0 s** | **76.1 %** | **18** |
| 1.5 s | 63.4 % | 41 |

The headline (reactions make most variants usable) holds for every value. The near-miss count does not:
quote it with its assumption.

## Quick start (Windows)

```powershell
git clone https://github.com/phanhieunghia353/replay-forge.git
cd replay-forge
python -m venv .venv
.venv\Scripts\python.exe -m pip install numpy scipy pytest
.venv\Scripts\python.exe -m pytest -q
```

You also need:

- **esmini v3.9.0**: `esmini-demo_Windows.zip` from the [releases](https://github.com/esmini/esmini/releases),
  unpacked into `tools\` (found automatically at `tools\esmini-demo\bin\esmini.exe`).
- **nuScenes** (not included, see its [terms of use](https://www.nuscenes.org/terms-of-use)):
  `v1.0-mini\*.json` and the map expansion v1.3 under `data\nuscenes\`. The mini JSON tables sit in the
  first ~20 MB of the public `v1.0-mini.tgz`:

  ```powershell
  curl.exe -r 0-20000000 -o head.tgz https://www.nuscenes.org/data/v1.0-mini.tgz
  tar.exe -xzf head.tgz -C data\nuscenes v1.0-mini
  ```

  Or bring your own data as CSV: [docs/dinh-dang-csv.md](docs/dinh-dang-csv.md).

## Web app

```powershell
.\real2sim.bat          # http://127.0.0.1:8765, runs fully offline
```

- **Simple mode**: pick a vehicle that has someone behind it, choose how hard it brakes and what it does
  next, hit *Create*. Followers react on screen, the verdict is one plain sentence, *Download* replays the
  scenario in esmini first and hands you `.xosc` + `.xodr` + `trajectories.csv` + `report.json`.
- **Technical mode**: exact parameters, reaction-time sensitivity, overlays (recorded ghosts, who follows
  whom, gap and TTC, measuring tool), timeline events, and a dock with charts, the parameter space,
  per-vehicle states, every validity check with its threshold and measured value, esmini replay error,
  source label quality, and provenance.
- Every parameter has a `?` that says what it is, how it is measured and where the number comes from.

## CLI

```powershell
.venv\Scripts\python.exe -m real2sim scenes                         # list scenes of the source
.venv\Scripts\python.exe -m real2sim replay  --scene scene-0061     # metric 1
.venv\Scripts\python.exe -m real2sim holdout                        # metric 1, held-out check
.venv\Scripts\python.exe -m real2sim events  --scene scene-0061     # metric 2
.venv\Scripts\python.exe -m real2sim events  --scene scene-0061 --reaction 1.5 --keep none --out out/sensitivity/r1.5
.venv\Scripts\python.exe -m real2sim report                         # out/<source>/summary.md
.venv\Scripts\python.exe -m real2sim --csv path\to\csv replay --scene my-scene
```

Results land in `out/<source>/<scene>/`. Runs write to a staging folder and swap in only when complete;
every result records the commit, esmini version and config it came from, and `report` flags tables that
mix runs.

## What "valid" means

A variant counts only if all seven pass, checked on every vehicle whose motion changed:

1. esmini replays the exported file (exit 0, every object logged while present)
2. acceleration <= 4 m/s², braking <= the vehicle's limit (cars 8, buses and trucks 5 m/s²), measured from
   positions so position jumps show up
3. no label error in the recording at the same spot (reported as a data problem, still rejected)
4. no two vehicles overlap, except with the ego (overlaps already in the labels are excused by relative position)
5. no tailgating (< 0.5 m above 3 m/s for > 0.5 s)
6. no merging, crossing or pedestrian contact: not simulated yet, so rejected instead of guessed
7. no vehicle that only just entered the data where the situation changed

A near miss for the ego: a vehicle on its path (same lane, in front or behind) within 1 m, or TTC < 1.5 s on
any side, closer than the same pair in the recording. A car passing in the next lane does not count.

## Limits, stated up front

- One kind of event: a lead vehicle brakes. No cut-ins, junction conflicts or crossing pedestrians yet.
- Vehicles react longitudinally only (brake, accelerate), never steer.
- Driver parameters (reaction, IDM a/b, jerk) are literature-based assumptions; only headway T and standstill
  gap s0 are fitted from 2 Hz labels.
- Exported scenarios are time-triggered trajectories: if the system under test drives differently from the
  reference driver, the other vehicles will not react to it.
- 10 urban scenes, slow traffic: no "hard braking" case has shown up yet.

## Layout

```
real2sim/            core: sources, tracks, reconstruction, xosc/xodr, esmini, behavior, events, report
real2sim/app/        local web app (stdlib HTTP server + plain JS, three.js vendored)
tests/               pytest, no nuScenes or esmini needed
docs/                design and metric definitions (Vietnamese)
```

Docs: [metrics and assumptions](docs/gia-dinh-va-chi-so.md) · [behaviour design](docs/thiet-ke-kich-ban-hanh-vi.md)
· [UI design](docs/thiet-ke-giao-dien.md) · [architecture](docs/kien-truc.md) · [CSV format](docs/dinh-dang-csv.md)

## Credits

- [nuScenes](https://www.nuscenes.org/) by Motional: data and map expansion (not redistributed here).
- [esmini](https://github.com/esmini/esmini) (MPL-2.0): OpenSCENARIO player used for every replay.
- [three.js](https://threejs.org/) 0.170.0 (MIT), vendored for the 3D view.
- Driver model: Treiber, Hennecke, Helbing (2000), IDM; Kesting, Treiber, Helbing (2010), enhanced IDM.
