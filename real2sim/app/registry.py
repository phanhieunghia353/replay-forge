"""The data sources the app knows, stored in <data>/sources.json (a small, hand-editable list).

Entry examples:
  {"id": "nuscenes-mini", "kind": "nuscenes", "label": "nuScenes v1.0-mini", "dataroot": "data/nuscenes", "version": "v1.0-mini"}
  {"id": "cong-ty-a", "kind": "csv", "label": "Dữ liệu công ty A", "path": "data/imported/cong-ty-a"}

On first start, data/nuscenes/v1.0-mini (if present) is registered. CSV files imported through the
app are copied to <data>/imported/<id>/ as tracks.csv (+ <scene>.xodr), so the source keeps working
even if the original file is moved.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from real2sim.sources import SourceError, load_source, parse_tracks_csv, slug


class Registry:
    def __init__(self, data_dir: str | Path, out_root: str | Path | None = None):
        self.data_dir = Path(data_dir)
        self.out_root = Path(out_root) if out_root is not None else None
        self.path = self.data_dir / "sources.json"
        self._lock = threading.Lock()
        if self.path.is_file():
            self._entries = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._entries = []
            mini = self.data_dir / "nuscenes" / "v1.0-mini"
            if mini.is_dir():
                self._entries.append({"id": "nuscenes-mini", "kind": "nuscenes", "label": "nuScenes v1.0-mini",
                                      "dataroot": str(self.data_dir / "nuscenes"), "version": "v1.0-mini"})
            self._save()

    def entries(self) -> list[dict]:
        with self._lock:
            return [dict(e) for e in self._entries]

    def entry(self, source_id: str) -> dict | None:
        return next((e for e in self.entries() if e["id"] == source_id), None)

    def add_nuscenes(self, dataroot: str, version: str, label: str = "") -> dict:
        entry = {"kind": "nuscenes", "dataroot": str(Path(dataroot)), "version": version.strip() or "v1.0-mini"}
        entry["id"] = self._free_id(slug(label) if label else f"nuscenes-{entry['version'].removeprefix('v1.0-')}")
        entry["label"] = label or f"nuScenes {entry['version']}"
        load_source(entry)  # raises SourceError with a readable message if the folder is wrong
        return self._append(entry)

    def add_csv(self, label: str, csv_text: str, xodr: dict[str, str] | None = None) -> dict:
        scenes = parse_tracks_csv(csv_text)  # validate before writing anything
        label = label.strip() or "Dữ liệu CSV"
        source_id = self._free_id(slug(label).lower())
        folder = self.data_dir / "imported" / source_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "tracks.csv").write_text(csv_text, encoding="utf-8")
        for name, text in (xodr or {}).items():
            scene = slug(Path(name).stem)
            if scene not in scenes:
                shutil.rmtree(folder, ignore_errors=True)
                raise SourceError(f"File đường '{name}' không ứng với cảnh nào trong CSV "
                                  f"(cần tên <cảnh>.xodr, các cảnh: {', '.join(sorted(scenes))}).")
            (folder / f"{scene}.xodr").write_text(text, encoding="utf-8")
        return self._append({"id": source_id, "kind": "csv", "label": label, "path": str(folder)})

    def remove(self, source_id: str) -> None:
        with self._lock:
            self._entries = [e for e in self._entries if e["id"] != source_id]
            self._save()

    # ------------------------------------------------------------------ helpers
    def _append(self, entry: dict) -> dict:
        with self._lock:
            self._entries.append(entry)
            self._save()
        return dict(entry)

    def _free_id(self, base: str) -> str:
        """An id no source uses, and whose imported-data and results folders do not exist yet (a removed
        source keeps its folders; reusing its id would mix its old results with the new data).
        Compared without case, as Windows folder names are."""
        taken = {e["id"].lower() for e in self.entries()}
        for folder in (self.data_dir / "imported", self.out_root):
            if folder is not None and folder.is_dir():
                taken |= {p.name.lower() for p in folder.iterdir()}
        candidate, k = base or "nguon", 2
        while candidate.lower() in taken:
            candidate, k = f"{base}-{k}", k + 1
        return candidate

    def _save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._entries, indent=1, ensure_ascii=False), encoding="utf-8")
