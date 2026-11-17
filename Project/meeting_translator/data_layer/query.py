"""Filtering criteria for stored records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..models import ProcessedRecord


@dataclass(frozen=True)
class RecordQuery:
    """Which records to keep.

    tones / languages / target_languages / speakers are lists of allowed values (None or empty
    = ignore that criterion). `languages` is the language the speaker actually used (as detected
    by the AI), `target_languages` the language it was translated into, `speakers` the speaker's name.

    match="all": a record must satisfy every criterion that has a selection (AND).
    match="any": a record must satisfy at least one of them (OR).
    outcome and meeting are extra narrowing filters that always apply (AND).
    """

    tones: Optional[Sequence[str]] = None
    languages: Optional[Sequence[str]] = None
    target_languages: Optional[Sequence[str]] = None
    speakers: Optional[Sequence[str]] = None
    match: str = "all"
    outcome: Optional[str] = None
    meeting: Optional[str] = None

    def matches(self, record: ProcessedRecord) -> bool:
        criteria = [
            (record.tone, self.tones), (record.detected_language, self.languages),
            (record.target_language, self.target_languages), (record.speaker_name, self.speakers),
        ]
        tests = [value in set(allowed) for value, allowed in criteria if allowed]
        if tests and not (any(tests) if self.match == "any" else all(tests)):
            return False
        if self.outcome is not None and record.outcome != self.outcome:
            return False
        if self.meeting is not None and record.meeting != self.meeting:
            return False
        return True
