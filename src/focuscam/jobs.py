from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "queued"
    current: int = 0
    total: int = 1
    message: str = "Queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def progress(self) -> float:
        return min(1.0, self.current / max(1, self.total))

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["progress"] = self.progress
        return payload


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        kind: str,
        task: Callable[[Callable[[int, int, str], None]], dict[str, Any]],
    ) -> Job:
        job = Job(job_id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self._jobs[job.job_id] = job

        def update(current: int, total: int, message: str) -> None:
            with self._lock:
                job.current = current
                job.total = max(1, total)
                job.message = message

        def run() -> None:
            with self._lock:
                job.status = "running"
            try:
                result = task(update)
            except Exception as exc:  # noqa: BLE001 - background jobs must surface all failures.
                traceback.print_exc()
                with self._lock:
                    job.status = "failed"
                    job.error = str(exc)
                    job.message = "Job failed"
                return
            with self._lock:
                job.status = "completed"
                job.current = job.total
                job.message = "Complete"
                job.result = result

        threading.Thread(target=run, name=f"focuscam-{kind}-{job.job_id[:8]}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)
