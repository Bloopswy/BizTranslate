"""Storage back-ends.

    RecordRepository (interface)
        ^
    FileRecordRepository (abstract base: path handling, missing/corrupt files, atomic save)
        ^                          ^
    JsonRecordRepository     CsvRecordRepository

DataManager only knows the RecordRepository interface (Dependency Inversion), so a new
storage format is one new subclass and no change anywhere else (Open/Closed).
"""

from __future__ import annotations

import csv
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List

from ..exceptions import RecordFormatError
from ..models import ProcessedRecord


class RecordRepository(ABC):
    """Interface (contract) for anything that can persist processed records."""

    @abstractmethod
    def load_all(self) -> List[ProcessedRecord]:
        """Every stored record. Must not raise for missing or corrupt storage (return [])."""

    @abstractmethod
    def save_all(self, records: List[ProcessedRecord]) -> bool:
        """Replace the stored records. Returns True on success, False on failure."""


class FileRecordRepository(RecordRepository, ABC):
    """Shared behaviour of file-based repositories; subclasses only define the file format."""

    def __init__(self, path: str):
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    @abstractmethod
    def _read_rows(self, handle) -> List[dict]:
        """Parse an open text file into a list of plain dicts. Raise ValueError if unusable."""

    @abstractmethod
    def _write_rows(self, handle, rows: List[dict]) -> None:
        """Write the plain dicts to an open text file."""

    def load_all(self) -> List[ProcessedRecord]:
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, "r", encoding="utf-8", newline="") as handle:
                rows = self._read_rows(handle)
        except (OSError, ValueError) as error:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
            logging.error("Could not read %s (%s); moving it aside", self._path, error)
            self._quarantine()
            return []
        records = []
        for position, row in enumerate(rows, start=1):
            try:
                records.append(ProcessedRecord.from_dict(row))
            except RecordFormatError as error:
                logging.warning("Skipping unreadable record %d in %s: %s", position, self._path, error)
        return records

    def save_all(self, records: List[ProcessedRecord]) -> bool:
        folder = os.path.dirname(self._path)
        temp_path = self._path + ".tmp"
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(temp_path, "w", encoding="utf-8", newline="") as handle:
                self._write_rows(handle, [record.to_dict() for record in records])
            os.replace(temp_path, self._path)  # atomic: a crash never leaves half a file
            return True
        except OSError as error:
            logging.error("Could not save %s: %s", self._path, error)
            return False

    def _quarantine(self) -> None:
        try:
            os.replace(self._path, self._path + ".corrupt")
        except OSError as error:
            logging.error("Could not move corrupt file: %s", error)


class JsonRecordRepository(FileRecordRepository):
    """Stores all records as one JSON list."""

    def _read_rows(self, handle) -> List[dict]:
        data = json.load(handle)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("top level must be a list of objects")
        return data

    def _write_rows(self, handle, rows: List[dict]) -> None:
        json.dump(rows, handle, ensure_ascii=False, indent=2, sort_keys=True)


class CsvRecordRepository(FileRecordRepository):
    """Stores records as CSV (one row each) - easy to open in a spreadsheet."""

    COLUMNS = [
        "meeting", "seq", "timestamp", "speaker", "speaker_name", "speaker_language", "listener_name",
        "target_language", "transcript", "translation", "detected_language", "language_confidence",
        "translation_confidence", "tone", "tone_confidence", "intensity", "score", "tone_reason",
        "outcome", "reasons", "input_type", "id",
    ]
    REASON_SEPARATOR = " | "

    def _read_rows(self, handle) -> List[dict]:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "id" not in reader.fieldnames:
            raise ValueError("not a records CSV file (no 'id' column)")
        rows = []
        for row in reader:
            row = dict(row)
            text = row.get("reasons") or ""
            row["reasons"] = [part for part in text.split(self.REASON_SEPARATOR) if part]
            rows.append(row)  # numbers stay text; ProcessedRecord.from_dict converts them
        return rows

    def _write_rows(self, handle, rows: List[dict]) -> None:
        writer = csv.DictWriter(handle, fieldnames=self.COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "reasons": self.REASON_SEPARATOR.join(row["reasons"])})


class RepositoryFactory:
    """Chooses the repository from the file extension. Add a format by registering a class."""

    _by_extension: Dict[str, type] = {".json": JsonRecordRepository, ".csv": CsvRecordRepository}

    @classmethod
    def register(cls, extension: str, repository_class: type) -> None:
        cls._by_extension[extension.lower()] = repository_class

    @classmethod
    def for_path(cls, path: str) -> RecordRepository:
        extension = os.path.splitext(path)[1].lower()
        return cls._by_extension.get(extension, JsonRecordRepository)(path)
