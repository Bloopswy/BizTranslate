import json
import logging
import os

DEFAULT_DATA_PATH = os.environ.get("DATA_FILE", os.path.join("data", "records.json"))
LEGACY_MEETING = "earlier-records"

def migrate_record(record):
    """Upgrade a record saved by an older version so every screen can read it."""
    migrated = dict(record)
    if "translation" not in migrated and "english_translation" in migrated:
        migrated["translation"] = migrated.pop("english_translation")
    if "intensity" not in migrated and "urgency" in migrated:
        migrated["intensity"] = migrated.pop("urgency")
    migrated.setdefault("meeting", LEGACY_MEETING)
    migrated.setdefault("speaker", "?")
    migrated.setdefault("speaker_name", "Earlier record")
    migrated.setdefault("target_language", "English")
    migrated.setdefault("seq", 0)
    return migrated

def _seq(record):
    value = record.get("seq", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def sort_records(records):
    """Stable, deterministic order: by meeting, then position in the meeting."""
    return sorted(records, key=lambda r: (str(r.get("meeting", "")), _seq(r),
                                          str(r.get("timestamp", "")), str(r.get("id", ""))))


def load_records(path=DEFAULT_DATA_PATH):
    """Load all records. Returns [] if the file is missing or corrupt."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("top level must be a list of objects")
        return [migrate_record(item) for item in data]
    except (OSError, ValueError) as error:
        logging.error("Could not read %s (%s); moving it aside", path, error)
        try:
            os.replace(path, path + ".corrupt")
        except OSError as move_error:
            logging.error("Could not move corrupt file: %s", move_error)
        return []

def list_meetings(records):
    return sorted({str(r.get("meeting", "")) for r in records if r.get("meeting")})


