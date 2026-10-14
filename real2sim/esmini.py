"""Run esmini headless and read its CSV log.

Flags used (esmini command reference, https://esmini.github.io/command-reference.html):
  --headless, --osc <file>, --fixed_timestep <dt>, --traj_filter <radius>, --csv_logger <file>.
CSV layout follows CSV_Logger in esmini EnvironmentSimulator/Modules/CommonMini/CommonMini.cpp:
six "key: value" preamble lines, then one header line starting with "Index [-]", then one row per
time step with a block of columns per entity ("#k Entity_Name [-]", "#k World_Position_X [m]", ...).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

COLUMNS = {
    "name": "Entity_Name [-]",
    "speed": "Current_Speed [m/s]",
    "x": "World_Position_X [m]",
    "y": "World_Position_Y [m]",
    "h": "World_Heading_Angle [rad]",
}


LOG_TIME_TOL = 1e-3  # s, a log must cover each track's time span to within this


class EsminiError(RuntimeError):
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED = [PROJECT_ROOT / "tools" / "esmini-demo" / "bin" / name for name in ("esmini.exe", "esmini")]


def find_esmini(explicit: str | None = None) -> Path | None:
    """First of: --esmini PATH, $ESMINI_BIN, esmini on PATH, tools/esmini-demo/bin/ in this project."""
    candidates = [explicit, os.environ.get("ESMINI_BIN"), shutil.which("esmini"), *BUNDLED]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


@dataclass
class RunResult:
    returncode: int
    csv_path: Path
    stdout: str
    stderr: str


def run_esmini(exe: Path, xosc: Path, csv_path: Path, dt: float = 0.05, timeout: float = 600) -> RunResult:
    """Run one scenario. esmini writes its own log.txt into the working directory (csv_path's folder).

    --traj_filter 0 disables esmini's merging of trajectory points closer than 0.1 m (its default),
    which otherwise makes slow objects freeze and jump between our 0.1 s vertices.
    """
    cmd = [str(exe), "--headless", "--osc", str(xosc.resolve()), "--fixed_timestep", str(dt)]
    cmd += ["--traj_filter", "0", "--csv_logger", str(csv_path.resolve())]
    proc = subprocess.run(cmd, cwd=csv_path.parent, capture_output=True, text=True, timeout=timeout)
    return RunResult(proc.returncode, csv_path, proc.stdout, proc.stderr)


@dataclass
class SimTrack:
    t: np.ndarray
    xy: np.ndarray
    yaw: np.ndarray
    speed: np.ndarray


def _split(line: str) -> list[str]:
    return [field.strip() for field in line.rstrip("\n").split(",")]


def read_csv_log(path: str | Path) -> dict[str, SimTrack]:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("Index [-]"))
    except StopIteration as exc:
        raise EsminiError(f"No CSV header line in {path}") from exc
    header = _split(lines[start])
    time_col = header.index("TimeStamp [s]")
    # Every entity has a block of the same columns; the header spells out block #1.
    first = [col for col, label in enumerate(header) if label.startswith("#1 ")]
    if not first:
        raise EsminiError(f"No entity columns in {path}")
    offsets = {}
    for col in first:
        rest = header[col].partition(" ")[2]
        for key, suffix in COLUMNS.items():
            if rest == suffix:
                offsets[key] = col - first[0]
    if len(offsets) != len(COLUMNS):
        raise EsminiError(f"Missing entity columns {set(COLUMNS) - set(offsets)} in {path}")
    width = len(first)

    # Each row holds one block per entity present at that time, in order. The header counts only the
    # entities present at the start: an entity added later (AddEntityAction) appends a block, and a
    # removed one (DeleteEntityAction) drops its block, so rows differ in length and names are read per row.
    rows: dict[str, list[tuple[float, ...]]] = {}
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        fields = _split(line)
        t = float(fields[time_col])
        for base in range(first[0], len(fields), width):
            cols = {key: base + off for key, off in offsets.items()}
            if max(cols.values()) >= len(fields) or not fields[cols["name"]]:
                continue
            rows.setdefault(fields[cols["name"]], []).append(
                (t, float(fields[cols["x"]]), float(fields[cols["y"]]), float(fields[cols["h"]]), float(fields[cols["speed"]]))
            )
    result = {}
    for name, data in rows.items():
        arr = np.array(data, dtype=float)
        result[name] = SimTrack(arr[:, 0], arr[:, 1:3], arr[:, 3], arr[:, 4])
    return result


def read_preamble(path: str | Path) -> dict[str, str]:
    """The "key: value" lines before the CSV header, e.g. {"esmini GIT TAG": "v3.9.0", ...}."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Index [-]"):
            break
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out


def log_problems(tracks, sim: dict[str, SimTrack], tol: float = LOG_TIME_TOL) -> list[str]:
    """What keeps a replay log from being scored: a track missing from it, a track whose logged time
    does not cover its own time span (interpolation would hold the edge value), or non-finite values."""
    problems = []
    for track in tracks:
        st = sim.get(track.name)
        if st is None or len(st.t) == 0:
            problems.append(f"missing {track.name}")
        elif not all(np.isfinite(a).all() for a in (st.t, st.xy, st.yaw, st.speed)):
            problems.append(f"non-finite values for {track.name}")
        elif st.t[0] > track.t[0] + tol or st.t[-1] < track.t[-1] - tol:
            problems.append(f"{track.name} logged {st.t[0]:.2f}-{st.t[-1]:.2f} s, "
                            f"needs {track.t[0]:.2f}-{track.t[-1]:.2f} s")
    return problems
