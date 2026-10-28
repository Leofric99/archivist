"""Background job execution with progress, logging and cancellation."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from ..core.common import Cancelled, Context, Operation, Plan, Reporter


class JobBusy(Exception):
    """Another job is already running."""


class Job:
    def __init__(self, op: Operation) -> None:
        self.id = uuid.uuid4().hex
        self.op_id = op.id
        self.op_label = op.label
        self.status = "running"  # running | done | cancelled | error
        self.error: Optional[str] = None
        self.logs: list = []
        self.progress = {"total": 0, "done": 0, "label": "", "fraction": 0.0}
        self.counts = {"ok": 0, "skipped": 0, "failed": 0}
        self.cancel_event = threading.Event()
        self.started = time.time()
        self.finished: Optional[float] = None
        self._lock = threading.Lock()

    def log(self, message: str, level: str = "info") -> None:
        with self._lock:
            self.logs.append({"message": message, "level": level})

    def set_progress(self, progress: dict) -> None:
        self.progress = progress

    def snapshot(self, since: int = 0) -> dict:
        with self._lock:
            logs = self.logs[since:]
            nxt = len(self.logs)
        return {
            "id": self.id, "op": self.op_id, "label": self.op_label, "status": self.status,
            "error": self.error, "progress": self.progress, "counts": self.counts,
            "logs": logs, "next": nxt,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def busy(self) -> bool:
        return any(j.status == "running" for j in self._jobs.values())

    def start(self, op: Operation, ctx: Context, plan: Plan) -> Job:
        with self._lock:
            if any(j.status == "running" for j in self._jobs.values()):
                raise JobBusy("Another operation is still running.")
            job = Job(op)
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, op, ctx, plan), daemon=True).start()
        return job

    def _run(self, job: Job, op: Operation, ctx: Context, plan: Plan) -> None:
        rep = Reporter(job.log, job.set_progress, job.cancel_event)
        status = "done"
        try:
            op.apply(ctx, plan, rep)
        except Cancelled:
            job.log("Cancelled.", "warn")
            status = "cancelled"
        except Exception as exc:
            job.log(f"Unexpected error: {exc}", "error")
            job.error = str(exc)
            status = "error"
        job.counts = {"ok": rep.n_ok, "skipped": rep.n_skipped, "failed": rep.n_failed}
        job.finished = time.time()
        job.status = status  # last, so readers never see a finished job with stale counts
