"""Background processing for the app: one worker thread runs queued jobs one at a time.

A job processes one scene (metric 1 then metric 2, see real2sim/pipeline.py) and reports its
progress so the browser can show a bar. Finished and failed jobs stay in the list until the app
restarts.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Callable


@dataclass
class Job:
    id: int
    source: str
    scene: str
    status: str = "queued"  # queued | running | done | failed
    progress: float = 0.0
    message: str = "đang chờ"
    error: str = ""
    log: list[str] = field(default_factory=list)
    started: float | None = None
    finished: float | None = None

    def public(self) -> dict:
        data = asdict(self)
        data["log"] = self.log[-20:]  # recent lines only
        return data


class JobRunner:
    """run(job, log, progress) does the work; on_done(job) runs after each job (success or not)."""

    def __init__(self, run: Callable, on_done: Callable[[Job], None] = lambda job: None):
        self._run, self._on_done = run, on_done
        self._jobs: dict[int, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True, name="real2sim-jobs").start()

    def submit(self, source: str, scene: str) -> Job:
        with self._lock:
            for job in self._jobs.values():  # do not queue the same scene twice
                if job.source == source and job.scene == scene and job.status in ("queued", "running"):
                    return job
            job = Job(next(self._ids), source, scene)
            self._jobs[job.id] = job
        self._queue.put(job)
        return job

    def list(self) -> list[dict]:
        with self._lock:
            return [job.public() for job in sorted(self._jobs.values(), key=lambda j: j.id)]

    def wait_idle(self, timeout: float = 60.0) -> bool:
        """For tests: block until no job is queued or running."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if all(j["status"] in ("done", "failed") for j in self.list()):
                return True
            time.sleep(0.05)
        return False

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            job.status, job.started, job.message = "running", time.time(), "đang chạy"

            def log(text: str, job=job) -> None:
                job.log.extend(str(text).splitlines())

            def progress(fraction: float, text: str, job=job) -> None:
                job.progress, job.message = max(0.0, min(1.0, fraction)), text

            try:
                self._run(job, log, progress)
                job.status, job.progress, job.message = "done", 1.0, "xong"
            except Exception as exc:  # report to the user, keep the worker alive
                job.status, job.error, job.message = "failed", str(exc), "lỗi"
                log(traceback.format_exc())
            finally:
                job.finished = time.time()
                self._on_done(job)
