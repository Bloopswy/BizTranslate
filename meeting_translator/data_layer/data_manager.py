"""DataManager: the in-memory collection of records plus loading, saving and querying."""

from __future__ import annotations

import threading
from typing import List, Optional, Tuple

from ..models import ProcessedRecord
from .query import RecordQuery
from .repositories import RecordRepository


class DataManager:
    """Holds every processed record (all meetings) and persists them via a RecordRepository.

    The repository is injected (aggregation): it exists independently of the manager and
    can be swapped (JSON, CSV, or a fake in tests).

    Thread-safe: a background worker adds records while the GUI reads them, so every
    access to the record list happens under one re-entrant lock (`_lock`).
    """

    def __init__(self, repository: RecordRepository):
        self._repository = repository
        self._records: List[ProcessedRecord] = []
        self._lock = threading.RLock()

    # ----- persistence -----
    def load(self) -> int:
        """Load stored records (missing/corrupt storage gives none). Returns how many were loaded."""
        loaded = list(self._repository.load_all())
        with self._lock:
            self._records = loaded
        return len(loaded)

    def save(self) -> bool:
        with self._lock:  # keep writers from interleaving file writes
            return self._repository.save_all(self.all())

    # ----- basic collection operations -----
    def all(self) -> List[ProcessedRecord]:
        with self._lock:
            return self._sorted(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def find_by_id(self, record_id: str) -> Optional[ProcessedRecord]:
        with self._lock:
            return next((r for r in self._records if r.id == record_id), None)

    def add(self, record: ProcessedRecord) -> None:
        """Add a record (replacing one with the same id)."""
        with self._lock:
            self._records = [r for r in self._records if r.id != record.id] + [record]

    # ----- meetings -----
    def meetings(self) -> List[str]:
        with self._lock:
            return sorted({r.meeting for r in self._records if r.meeting})

    def meeting_records(self, meeting: str) -> List[ProcessedRecord]:
        """All sentences of one meeting, oldest first."""
        with self._lock:
            return self._sorted([r for r in self._records if r.meeting == meeting])

    def next_sequence(self, meeting: str) -> int:
        """Position the next sentence will take in this meeting (1, 2, 3, ...)."""
        with self._lock:
            numbers = [r.seq for r in self._records if r.meeting == meeting]
        return max(numbers) + 1 if numbers else 1

    def last_sentences(self, meeting: str, count: int) -> List[ProcessedRecord]:
        """The last `count` sentences of the meeting, oldest first."""
        return self.meeting_records(meeting)[-count:] if count > 0 else []

    def latest_with_context(self, meeting: str, context_count: int) -> Tuple[Optional[ProcessedRecord], List[ProcessedRecord]]:
        """(latest sentence or None, the `context_count` sentences before it)."""
        rows = self.meeting_records(meeting)
        if not rows:
            return None, []
        earlier = rows[:-1]
        return rows[-1], (earlier[-context_count:] if context_count > 0 else [])

    # ----- querying -----
    def query(self, query: RecordQuery) -> List[ProcessedRecord]:
        with self._lock:
            return self._sorted([r for r in self._records if query.matches(r)])

    @staticmethod
    def _sorted(records: List[ProcessedRecord]) -> List[ProcessedRecord]:
        """Stable, deterministic order: by meeting, then position in the meeting."""
        return sorted(records, key=lambda r: (r.meeting, r.seq, r.timestamp, r.id))
