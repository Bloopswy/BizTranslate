"""Presentation: turning records into text, and exporters (polymorphic output formats)."""

from __future__ import annotations

import csv
import io
import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import List, Optional

from ..models import ClockFormatter, ProcessedRecord


class RecordFormatter:
    """Readable text views of records, in one time zone."""

    def __init__(self, tz_name: Optional[str] = None):
        self._tz = tz_name

    @staticmethod
    def direction(record: ProcessedRecord) -> str:
        return "%s (%s) -> %s (%s)" % (record.speaker_name, record.speaker_language,
                                       record.listener_name, record.target_language)

    def sentence(self, record: ProcessedRecord) -> str:
        """Detailed multi-line view of one sentence."""
        return "\n".join([
            "[%s] %s  [%s]" % (ClockFormatter.format(record.timestamp, self._tz), self.direction(record), record.outcome),
            "    Said       : %s" % record.transcript,
            "    Translated : %s" % record.translation,
            "    Tone       : %s (confidence %.2f), intensity %s/5, attention score %s/100" % (
                record.tone, record.analysis.tone_confidence, record.intensity, record.score),
            "    Note       : %s" % "; ".join(record.reasons),
        ])

    def short_sentence(self, record: ProcessedRecord) -> str:
        """Compact two-line view used for the 'previous sentences' list."""
        return "[%s] %s (%s): %s\n           -> %s" % (
            ClockFormatter.format(record.timestamp, self._tz), record.speaker_name,
            record.speaker_language, record.transcript, record.translation)

    def conversation(self, latest: Optional[ProcessedRecord], previous: List[ProcessedRecord]) -> str:
        if latest is None:
            return "Nothing has been said in this meeting yet."
        lines = ["--- Latest translation ---", self.sentence(latest),
                 "\n--- Previous %d sentences ---" % len(previous) if previous else "\n(no earlier sentences)"]
        lines.extend(self.short_sentence(record) for record in previous)
        return "\n".join(lines)

    def transcript(self, records: List[ProcessedRecord]) -> str:
        if not records:
            return "No sentences."
        return "\n".join(self.short_sentence(record) for record in records)

    @staticmethod
    def summary(records: List[ProcessedRecord]) -> str:
        if not records:
            return "No records yet."
        lines = ["Total sentences: %d" % len(records)]
        for title, getter in (("By outcome", lambda r: r.outcome), ("By speaker", lambda r: r.speaker_name),
                              ("By language spoken", lambda r: r.detected_language), ("By tone", lambda r: r.tone)):
            counts = Counter(getter(r) for r in records)
            lines.append("%s: %s" % (title, ", ".join("%s=%d" % (name, counts[name]) for name in sorted(counts))))
        return "\n".join(lines)

    @staticmethod
    def safe_filename(text: str) -> str:
        """A file-name-friendly version of a meeting name."""
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("._") or "meeting"


class Exporter(ABC):
    """Interface: render records as text in some file format."""

    extension: str

    @abstractmethod
    def export(self, records: List[ProcessedRecord]) -> str:
        """The records as text."""


class CsvExporter(Exporter):
    extension = ".csv"
    COLUMNS = [
        "meeting", "seq", "timestamp", "speaker_name", "speaker_language", "listener_name", "target_language",
        "transcript", "translation", "detected_language", "language_confidence", "translation_confidence",
        "tone", "tone_confidence", "intensity", "score", "tone_reason", "outcome", "reasons", "input_type", "id",
    ]

    def export(self, records):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = record.to_dict()
            row["reasons"] = "; ".join(row["reasons"])
            writer.writerow(row)
        return buffer.getvalue()


class JsonExporter(Exporter):
    extension = ".json"

    def export(self, records):
        return json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2)


class TextExporter(Exporter):
    """Plain-text meeting minutes: one block per sentence with date and time."""

    extension = ".txt"

    def __init__(self, tz_name: Optional[str] = None):
        self._tz = tz_name

    def export(self, records):
        blocks = []
        for r in records:
            blocks.append("[%s] %s\n  Said: %s\n  Translation: %s\n  Tone: %s\n  Flag: %s" % (
                ClockFormatter.format(r.timestamp, self._tz, with_date=True), RecordFormatter.direction(r),
                r.transcript, r.translation, r.tone, r.outcome))
        return "\n\n".join(blocks) + ("\n" if blocks else "")
