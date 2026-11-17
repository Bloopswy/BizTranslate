"""ADVANCED FEATURE: threading.

Calling the AI takes seconds per sentence. Run on the main thread, that freezes the GUI.
BackgroundProcessor owns ONE worker thread that takes jobs from a queue and runs them through
the MeetingPipeline, so the interface stays responsive and shows live progress.

    BackgroundProcessor *-- worker thread, queue      (composition: owns their lifecycle)
    BackgroundProcessor --> MeetingPipeline           (association)
    Job                                               (thread-safe progress object, shared with the UI)

Why one worker and not many? Each sentence is sent to the AI together with the previous few
sentences of the same meeting, so sentences must be processed IN ORDER. One worker keeps that
guarantee while still never blocking the caller.
"""

from __future__ import annotations

import itertools
import logging
import queue
import threading
from typing import Dict, Iterable, List, Optional

from .models import Utterance
from .pipeline import MeetingPipeline, ProcessStatus


class Job:
    """A batch of sentences being processed. Safe to read from any thread."""

    CANCELLED = "cancelled"

    def __init__(self, job_id: int, utterances: Iterable[Utterance]):
        self._id = job_id
        self._utterances: List[Utterance] = list(utterances)
        self._counts: Dict[str, int] = {status.value: 0 for status in ProcessStatus}
        self._counts[self.CANCELLED] = 0
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._cancel_requested = threading.Event()

    # ----- read by the UI -----
    @property
    def id(self) -> int:
        return self._id

    @property
    def total(self) -> int:
        return len(self._utterances)

    @property
    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)

    @property
    def done(self) -> int:
        """Sentences dealt with so far (processed, skipped, failed or cancelled)."""
        return sum(self.counts.values())

    @property
    def progress(self) -> float:
        return 1.0 if self.total == 0 else self.done / self.total

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the job is finished (True) or the timeout passes (False)."""
        return self._finished.wait(timeout)

    def cancel(self) -> None:
        """Ask the worker to stop before the next sentence."""
        self._cancel_requested.set()

    # ----- used by the worker -----
    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    def utterances(self) -> List[Utterance]:
        return list(self._utterances)

    def record(self, outcome: str) -> None:
        with self._lock:
            self._counts[outcome] += 1

    def finish(self) -> None:
        self._finished.set()


class BackgroundProcessor:
    """Runs jobs one after another on a daemon worker thread."""

    _STOP = object()  # sentinel that tells the worker to exit

    def __init__(self, pipeline: MeetingPipeline):
        self._pipeline = pipeline
        self._queue: "queue.Queue" = queue.Queue()
        self._ids = itertools.count(1)
        self._start_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def submit(self, utterances: Iterable[Utterance]) -> Job:
        """Queue sentences for processing and return immediately with a Job to watch."""
        job = Job(next(self._ids), utterances)
        self._ensure_running()
        self._queue.put(job)
        return job

    def shutdown(self, wait: bool = True, timeout: float = 5.0) -> None:
        """Stop the worker after the queued jobs finish."""
        with self._start_lock:
            thread, self._thread = self._thread, None
        if thread is not None:
            self._queue.put(self._STOP)
            if wait:
                thread.join(timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _ensure_running(self) -> None:
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, name="translator-worker", daemon=True)
                self._thread.start()

    def _work(self) -> None:
        while True:
            job = self._queue.get()
            if job is self._STOP:
                return
            self._run_job(job)

    def _run_job(self, job: Job) -> None:
        try:
            for utterance in job.utterances():
                if job.cancel_requested:
                    job.record(Job.CANCELLED)
                    continue
                try:
                    job.record(self._pipeline.process(utterance).value)
                except Exception:  # noqa: BLE001 - one bad sentence must never kill the worker
                    logging.exception("Unexpected error while processing %s", utterance.id)
                    job.record(ProcessStatus.FAILED.value)
        finally:
            job.finish()
