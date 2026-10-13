"""Data layer - system memory across runs.

Stores processed records in a single JSON file. Missing or corrupt files never
crash the program: a missing file means "no records yet", a corrupt file is moved
aside (so nothing is lost) and the system starts fresh.
"""

import json
import logging
import os

DEFAULT_DATA_PATH = os.environ.get("DATA_FILE", os.path.join("data", "records.json"))


def sort_records(records):
    """Stable, deterministic ordering so identical input gives identical files."""
    return sorted(records, key=lambda r: (r.get("timestamp", ""), r.get("id", "")))


def load_records(path=DEFAULT_DATA_PATH):
    """Load all records. Returns [] if the file is missing or corrupt."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("top level must be a list of objects")
        return data
    except (OSError, ValueError) as error:
        logging.error("Could not read %s (%s); moving it aside", path, error)
        try:
            os.replace(path, path + ".corrupt")
        except OSError as move_error:
            logging.error("Could not move corrupt file: %s", move_error)
        return []


def save_records(records, path=DEFAULT_DATA_PATH):
    """Write all records atomically. Returns True on success."""
    folder = os.path.dirname(path)
    try:
        if folder:
            os.makedirs(folder, exist_ok=True)
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(sort_records(records), handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp_path, path)
        return True
    except OSError as error:
        logging.error("Could not save %s: %s", path, error)
        return False


def find_by_id(records, record_id):
    for record in records:
        if record.get("id") == record_id:
            return record
    return None


def add_record(records, record):
    """Return a new list with `record` added (or replacing one with the same id)."""
    remaining = [r for r in records if r.get("id") != record.get("id")]
    return remaining + [record]


def filter_records(records, outcome=None, tone=None, language=None, min_priority=None):
    """Return records matching every criterion that is not None."""
    matches = []
    for record in records:
        if outcome is not None and record.get("outcome") != outcome:
            continue
        if tone is not None and record.get("tone") != tone:
            continue
        if language is not None and record.get("detected_language") != language:
            continue
        if min_priority is not None and record.get("priority_score", 0) < min_priority:
            continue
        matches.append(record)
    return sort_records(matches)
