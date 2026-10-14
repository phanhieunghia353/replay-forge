"""Tiny HTTP server for the web app (Python standard library only).

Routes (all JSON except the static files)
  GET  /                               static/index.html
  GET  /static/<path>                  files under static/ (no access outside it)
  GET  /api/status                     Workspace.status()
  GET  /api/sources                    Workspace.sources()
  GET  /api/scenes?source=<id>         Workspace.scene_list(id)
  GET  /api/scene?source=<id>&name=<s> Workspace.scene(id, s)
  GET  /api/variant?source=<id>&name=<s>&method=<baseline|pilot>&id=<variant id>   Workspace.variant(...)
  GET  /api/jobs                       Workspace.jobs()
  GET  /api/download?source=<id>&name=<s>&id=<export id>   the .zip written by /api/export
  POST /api/sources                    {"kind": "nuscenes", "dataroot", "version", "label"}
                                       {"kind": "csv", "label", "csv_text", "xodr": {"<file>.xodr": text}}
  POST /api/sources/remove             {"id"}
  POST /api/process                    {"source", "scenes": [...] or null for every unprocessed scene}
  POST /api/simulate                   {"source", "name", "actor", "t0", "decel", "target", "dwell", "react", "reaction"}
  POST /api/export                     same body: replay in esmini, write the files, answer with their report

Data problems (SourceError, PipelineError) answer 400 with {"error": message for the user}.
Only binds to 127.0.0.1 by default: the app is meant to run on the user's own machine.
"""

from __future__ import annotations

import json
import math
import mimetypes
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from real2sim.app.api import Workspace
from real2sim.pipeline import PipelineError
from real2sim.sources import SourceError

STATIC = Path(__file__).parent / "static"
MAX_BODY = 200 * 1024 * 1024  # bytes; CSV uploads arrive as JSON text
# Explicit types: on Windows, mimetypes reads the registry and may report .js as text/plain,
# which browsers refuse to run as a module.
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                 ".csv": "text/csv; charset=utf-8"}


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


def make_handler(workspace: Workspace):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the console quiet; errors are still reported
            pass

        # ---------------------------------------------------------- routing
        def do_GET(self):
            self._handle(self._get)

        def do_POST(self):
            self._handle(self._post)

        def _get(self, path: str, query: dict):
            if path == "/":
                return self._file(STATIC / "index.html")
            if path.startswith("/static/"):
                return self._file(STATIC / path[len("/static/"):])
            if path == "/api/status":
                return self._json(workspace.status())
            if path == "/api/sources":
                return self._json(workspace.sources())
            if path == "/api/scenes":
                return self._json(workspace.scene_list(self._need(query, "source")))
            if path == "/api/scene":
                return self._json(workspace.scene(self._need(query, "source"), self._need(query, "name")))
            if path == "/api/variant":
                return self._json(workspace.variant(self._need(query, "source"), self._need(query, "name"),
                                                    self._need(query, "method"), self._need(query, "id")))
            if path == "/api/jobs":
                return self._json(workspace.jobs())
            if path == "/api/download":
                file = workspace.download(self._need(query, "source"), self._need(query, "name"),
                                          self._need(query, "id"))
                return self._send(file.read_bytes(), "application/zip",
                                  {"Content-Disposition": f'attachment; filename="{file.name}"'})
            raise ApiError(HTTPStatus.NOT_FOUND, f"Unknown path {path}")

        def _post(self, path: str, query: dict):
            body = self._body()
            if path == "/api/sources":
                if body.get("kind") == "nuscenes":
                    return self._json(workspace.add_nuscenes(body.get("dataroot", ""), body.get("version", ""),
                                                             body.get("label", "")))
                if body.get("kind") == "csv":
                    return self._json(workspace.add_csv(body.get("label", ""), body.get("csv_text", ""),
                                                        body.get("xodr") or {}))
                raise ApiError(HTTPStatus.BAD_REQUEST, "kind phải là 'nuscenes' hoặc 'csv'")
            if path == "/api/sources/remove":
                workspace.remove_source(self._need(body, "id"))
                return self._json({"ok": True})
            if path == "/api/process":
                return self._json(workspace.process(self._need(body, "source"), body.get("scenes")))
            if path == "/api/simulate":
                return self._json(workspace.simulate_event(self._need(body, "source"), self._need(body, "name"), body))
            if path == "/api/export":
                return self._json(workspace.export_event(self._need(body, "source"), self._need(body, "name"), body))
            raise ApiError(HTTPStatus.NOT_FOUND, f"Unknown path {path}")

        def _handle(self, route):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                route(url.path, query)
            except ApiError as exc:
                self._json({"error": str(exc)}, exc.status)
            except (SourceError, PipelineError) as exc:  # the user's data or setup: explain, do not crash
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                traceback.print_exc()
                self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        # ---------------------------------------------------------- helpers
        @staticmethod
        def _need(values: dict, key: str) -> str:
            value = values.get(key)
            if not value:
                raise ApiError(HTTPStatus.BAD_REQUEST, f"Thiếu '{key}'")
            return value

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Dữ liệu gửi lên quá lớn (tối đa 200 MB).")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError as exc:
                raise ApiError(HTTPStatus.BAD_REQUEST, f"JSON không hợp lệ: {exc}") from exc
            if not isinstance(data, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Cần một đối tượng JSON")
            return data

        def _file(self, path: Path):
            path = path.resolve()
            if STATIC.resolve() not in path.parents or not path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "File not found")
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            content_type = CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: HTTPStatus = HTTPStatus.OK):
            body = json.dumps(clean(data), allow_nan=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8", status=status)

        def _send(self, body: bytes, content_type: str, headers: dict | None = None,
                  status: HTTPStatus = HTTPStatus.OK):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def clean(value):
    """JSON-safe copy: inf/nan become None (JSON has no infinity), numpy scalars become floats."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if hasattr(value, "__float__"):
        number = float(value)
        return number if math.isfinite(number) else None
    return str(value)


def serve(workspace: Workspace, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(workspace))
