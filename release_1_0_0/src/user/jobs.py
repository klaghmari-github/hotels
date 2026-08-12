"""
Jobs asynchrones avec avancement pour operations longues (estimation, optim).

Stockage en memoire process (suffisant pour monolithe Flask threaded).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class JobState:
    job_id: str
    kind: str
    status: str = "pending"  # pending | running | done | error
    done: int = 0
    total: int = 1
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_public(self) -> dict[str, Any]:
        total = max(int(self.total), 1)
        done = max(0, min(int(self.done), total))
        pct = round(100.0 * done / total, 1)
        if self.status == "done":
            pct = 100.0
        out: dict[str, Any] = {
            "ok": True,
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "done": done,
            "total": total,
            "pct": pct,
            "message": self.message,
        }
        if self.status == "done" and self.result is not None:
            out["result"] = self.result
        if self.status == "error":
            out["error"] = self.error or "erreur"
            out["ok"] = False
        return out


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}

    def create(self, kind: str, total: int = 1, message: str = "En attente…") -> JobState:
        job_id = uuid.uuid4().hex[:12]
        job = JobState(
            job_id=job_id,
            kind=kind,
            status="pending",
            total=max(total, 1),
            message=message,
        )
        with self._lock:
            self._jobs[job_id] = job
            self._purge_old_unlocked()
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        done: int | None = None,
        total: int | None = None,
        message: str | None = None,
        status: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if done is not None:
                job.done = max(0, int(done))
            if total is not None:
                job.total = max(1, int(total))
            if message is not None:
                job.message = str(message)
            if status is not None:
                job.status = status
            job.updated_at = time.time()

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "done"
            job.done = job.total
            job.message = "Termine"
            job.result = result
            job.updated_at = time.time()

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "error"
            job.error = str(error)
            job.message = str(error)
            job.updated_at = time.time()

    def progress_callback(self, job_id: str) -> Callable[..., None]:
        """
        Callback(done, total, message) pour les moteurs metier.
        """

        def _cb(done: int, total: int, message: str = "") -> None:
            self.update(
                job_id,
                done=done,
                total=total,
                message=message or "",
                status="running",
            )

        return _cb

    def _purge_old_unlocked(self, max_age_s: float = 3600.0, max_jobs: int = 100) -> None:
        now = time.time()
        stale = [
            jid
            for jid, j in self._jobs.items()
            if now - j.updated_at > max_age_s
        ]
        for jid in stale:
            del self._jobs[jid]
        if len(self._jobs) > max_jobs:
            ordered = sorted(self._jobs.values(), key=lambda j: j.updated_at)
            for j in ordered[: len(self._jobs) - max_jobs]:
                self._jobs.pop(j.job_id, None)


# singleton process
JOB_STORE = JobStore()
