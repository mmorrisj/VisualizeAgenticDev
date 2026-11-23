"""Background jobs for the app: a class run or a bring-your-own test run.

In-process threads, so the app must run as a single process (uvicorn's default,
one worker). The runs themselves are stored as they finish, so a page reload
or a restart loses only the progress counter, not results.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    total: int = 0
    done: int = 0
    status: str = "running"            # running, done, error
    error: str = ""
    requests: dict = field(default_factory=dict)  # harness round: item key -> requests so far
    info: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def tick(self, *_):
        with self._lock:
            self.done += 1


class JobRunner:
    def __init__(self, inline: bool = False, workers: int = 4):
        self.inline = inline
        self.jobs: dict[str, Job] = {}
        self._pool = None if inline else ThreadPoolExecutor(max_workers=workers, thread_name_prefix="promptlab-job")

    def start(self, job: Job, work: Callable[[Job], None]) -> Job:
        self.jobs[job.id] = job

        def run():
            try:
                work(job)
                job.status = "done"
            except Exception as err:  # noqa: BLE001 - shown on the page, never swallowed
                job.status, job.error = "error", f"{type(err).__name__}: {err}"
                traceback.print_exc()

        if self.inline:
            run()
        else:
            self._pool.submit(run)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def shutdown(self):
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
