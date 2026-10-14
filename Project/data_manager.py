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

# FOR MEETINGS

def list_meetings(records):
    return sorted({str(r.get("meeting", "")) for r in records if r.get("meeting")})

def meeting_records(records, meeting):
    """All sentences of one meeting, oldest first."""
    return sort_records([r for r in records if r.get("meeting") == meeting])

def next_sequence(records, meeting):
    """Position the next sentence will take in this meeting (1, 2, 3, ...)."""
    numbers = [_seq(r) for r in records if r.get("meeting") == meeting]
    return max(numbers) + 1 if numbers else 1

def latest_with_context(records, meeting, context_count):
    """Returns (latest sentence or None, the `context_count` sentences before it)."""
    rows = meeting_records(records, meeting)
    if not rows:
        return None, []
    earlier = rows[:-1]
    return rows[-1], (earlier[-context_count:] if context_count > 0 else [])

def last_sentences(records, meeting, count):
    """The last `count` sentences of the meeting, oldest first."""
    if count <= 0:
        return []
    return meeting_records(records, meeting)[-count:]


# FOR FILTERING

def filter_records_multi(records, tones=None, languages=None, target_languages=None, speakers=None,
                         match="all", outcome=None, meeting=None):
    """Filter by tones and/or languages (and/or speaker).

    tones / languages / target_languages / speakers are lists of allowed values (None or empty =
    ignore that criterion). `languages` is the language the speaker actually used (as detected by the
    AI), `target_languages` the language it was translated into, `speakers` the speaker's name.

    match="all": a record must satisfy every criterion that has a selection (AND).
    match="any": a record must satisfy at least one of them (OR).
    outcome and meeting are extra narrowing filters that always apply (AND).
    """
    criteria = []
    for field, allowed in (("tone", tones), ("detected_language", languages),
                           ("target_language", target_languages), ("speaker_name", speakers)):
        if allowed:
            criteria.append((field, set(allowed)))

    matches = []
    for record in records:
        if criteria:
            tests = [record.get(field) in allowed for field, allowed in criteria]
            if not (any(tests) if match == "any" else all(tests)):
                continue
        if outcome is not None and record.get("outcome") != outcome:
            continue
        if meeting is not None and record.get("meeting") != meeting:
            continue
        matches.append(record)
    return sort_records(matches)
