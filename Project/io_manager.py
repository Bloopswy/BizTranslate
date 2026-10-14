"""Input/Output layer.

Every boundary between the system and the user lives here: every print() and input()
call, every Streamlit widget, the speech-to-text step, and the reading of meeting files.
It turns what the user says, types or uploads into clean "sentence" records.

A meeting has two parties, A and B. Each speaks English, Indonesian or Chinese. A
sentence spoken by one party is translated into the other party's language.
"""

import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

INPUT_DIR = os.environ.get("INPUT_DIR", "input")
LANGUAGES = ["English", "Indonesian", "Chinese"]
DETECTED_LANGUAGES = LANGUAGES + ["Other"]  # what the AI can report the speaker used
LANGUAGE_TO_SPEECH_CODE = {"English": "en-US", "Indonesian": "id-ID", "Chinese": "zh-CN"}
PARTY_IDS = ["A", "B"]
MAX_SENTENCE_CHARS = 2000
MAX_NAME_CHARS = 40
MAX_MEETING_CHARS = 60
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # largest recording we will transcribe
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")  # tiny/base/small/medium: bigger = more accurate, slower
WHISPER_TO_SPEECH_CODE = {"en": "en-US", "zh": "zh-CN", "id": "id-ID"}
SPEECH_CODE_TO_WHISPER = {code: short for short, code in WHISPER_TO_SPEECH_CODE.items()}
RECORDER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "recorder.html")

TONE_ORDER = ["neutral", "happy", "grateful", "sad", "anxious", "frustrated", "angry", "urgent"]
OUTCOME_ORDER = ["TENSION", "CHECK", "ACCEPT", "REJECT"]
OUTCOME_ICONS = {
    "TENSION": "\U0001F534", "CHECK": "\U0001F7E1", "ACCEPT": "\U0001F7E2", "REJECT": "\u26AA",
    "ESCALATE": "\U0001F534", "REVIEW": "\U0001F7E1",  # names used by older versions
}
AUTO_TIMEZONE = "Auto (browser)"
TIMEZONE_CHOICES = [
    AUTO_TIMEZONE, "UTC", "Asia/Singapore", "Asia/Jakarta", "Asia/Shanghai", "Asia/Hong_Kong",
    "Asia/Tokyo", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney",
]

def valid_timestamp(value):
    """The timestamp text if it is a valid ISO 8601 time, else ''."""
    if not isinstance(value, str):
        return ""
    try:
        datetime.fromisoformat(value.strip())
    except ValueError:
        return ""
    return value.strip()

def load_env_file(path=".env"):
    """Load KEY=VALUE lines from a .env file into os.environ.

    Variables that are already set in the environment win. A missing or unreadable
    file is fine. Returns the number of variables loaded.
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return 0
    loaded = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded

def ask(prompt):
    """input() wrapper. End-of-input (e.g. no terminal attached) acts like 'quit'."""
    try:
        return input(prompt).strip()
    except EOFError:
        return None

def prompt_choice(prompt, valid_choices):
    """Re-prompt until the answer is one of `valid_choices`. None means input ended."""
    while True:
        answer = ask(prompt)
        if answer is None:
            return None
        if answer in valid_choices:
            return answer
        show_error("please enter one of: " + ", ".join(c if c else "(just press Enter)" for c in valid_choices))

def prompt_sentence():
    """Ask for one typed sentence. Returns the text or None if input ended."""
    while True:
        text = ask("Sentence: ")
        if text is None:
            return None
        if not text:
            show_error("the sentence cannot be empty")
        elif len(text) > MAX_SENTENCE_CHARS:
            show_error("the sentence is too long (max %d characters)" % MAX_SENTENCE_CHARS)
        else:
            return text

def prompt_speaker(setup):
    """Returns 'A' or 'B', or None if input ended."""
    show_message("Who is speaking?  1) %s   2) %s" % (describe_party(setup, "A"), describe_party(setup, "B")))
    choice = prompt_choice("Speaker 1-2: ", ["1", "2"])
    return None if choice is None else PARTY_IDS[int(choice) - 1]

def prompt_language_or_keep(label, current):
    show_message("%s: 1) English  2) Indonesian  3) Chinese  (Enter keeps %s)" % (label, current))
    choice = prompt_choice("Choice: ", ["", "1", "2", "3"])
    if choice is None:
        return None
    return current if choice == "" else LANGUAGES[int(choice) - 1]

def prompt_filter(setup):
    """Ask how to filter. Returns keyword arguments for data_manager.filter_records_multi, or None."""
    show_message("Filter by: 1) tone  2) language spoken  3) translated into  4) speaker  5) outcome")
    choice = prompt_choice("Filter 1-5: ", ["1", "2", "3", "4", "5"])
    if choice is None:
        return None
    if choice == "1":
        value = prompt_choice("Tone (%s): " % "/".join(TONE_ORDER), TONE_ORDER)
        return None if value is None else {"tones": [value]}
    if choice == "2":
        value = prompt_choice("Language (%s): " % "/".join(DETECTED_LANGUAGES), DETECTED_LANGUAGES)
        return None if value is None else {"languages": [value]}
    if choice == "3":
        value = prompt_choice("Language (%s): " % "/".join(LANGUAGES), LANGUAGES)
        return None if value is None else {"target_languages": [value]}
    if choice == "4":
        show_message("1) %s   2) %s" % (describe_party(setup, "A"), describe_party(setup, "B")))
        value = prompt_choice("Speaker 1-2: ", ["1", "2"])
        return None if value is None else {"speakers": [setup["parties"][PARTY_IDS[int(value) - 1]]["name"]]}
    value = prompt_choice("Outcome (%s): " % "/".join(OUTCOME_ORDER), OUTCOME_ORDER)
    return None if value is None else {"outcome": value}

def prompt_file_choice(files):
    """Let the user pick one file (or all). Returns a list of file names, or None."""
    if not files:
        show_error("no .json or .txt files found in the '%s' folder" % INPUT_DIR)
        return None
    show_message("\nFiles in '%s':" % INPUT_DIR)
    for number, name in enumerate(files, start=1):
        show_message("  %d. %s" % (number, name))
    show_message("  A. all files")
    valid = [str(n) for n in range(1, len(files) + 1)] + ["A", "a"]
    choice = prompt_choice("Choose a file: ", valid)
    if choice is None:
        return None
    if choice.lower() == "a":
        return files
    return [files[int(choice) - 1]]

def list_input_files(folder=INPUT_DIR):
    """Names of .json / .txt files in the input folder (sorted)."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(n for n in names if n.lower().endswith((".json", ".txt")))

def prompt_setup(current):
    """Ask for meeting name, party names and languages (Enter keeps the current value).
    Returns a new setup, or None if input ended."""
    raw = {"meeting": ask("Meeting name [%s]: " % current["meeting"]), "parties": {}}
    if raw["meeting"] is None:
        return None
    for party_id in PARTY_IDS:
        party = current["parties"][party_id]
        name = ask("Name of party %s [%s]: " % (party_id, party["name"]))
        language = prompt_language_or_keep("Language of party %s" % party_id, party["language"])
        if name is None or language is None:
            return None
        raw["parties"][party_id] = {"name": name or party["name"], "language": language}
    return normalise_setup(raw, current)

def describe_party(setup, party_id):
    party = setup["parties"][party_id]
    return "%s (%s)" % (party["name"], party["language"])

def format_menu(setup, context_count):
    return (
        "\n=== Meeting Translator ===\n"
        "Meeting: %s\n"
        "  A: %s    B: %s\n"
        "1. Say a sentence (type it)\n"
        "2. Process meeting files from the input folder\n"
        "3. Show the latest sentence and the previous %d\n"
        "4. View the full transcript\n"
        "5. Filter records\n"
        "6. Summary\n"
        "7. Meeting setup (names and languages)\n"
        "8. Quit" % (setup["meeting"], describe_party(setup, "A"), describe_party(setup, "B"), context_count)
    )

def prompt_menu(setup, context_count=3):
    show_message(format_menu(setup, context_count))
    return prompt_choice("Choose 1-8: ", [str(n) for n in range(1, 9)])


# ---------- meeting setup and sentence records ----------

def default_meeting_name():
    return "meeting-" + datetime.now().strftime("%Y-%m-%d")


def default_setup():
    """A fresh two-party meeting: Party A speaks English, Party B speaks Indonesian."""
    return {
        "meeting": default_meeting_name(),
        "parties": {
            "A": {"name": "Party A", "language": "English"},
            "B": {"name": "Party B", "language": "Indonesian"},
        },
    }


def clean_label(text, fallback, limit):
    """A short single-line label (names are put into prompts, so keep them tidy)."""
    if not isinstance(text, str):
        return fallback
    cleaned = " ".join(text.split())
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())[:limit].strip()
    return cleaned or fallback


def normalise_setup(raw, fallback=None):
    """Validate a meeting setup. Bad or missing values fall back to `fallback` (or the defaults)."""
    base = fallback if fallback is not None else default_setup()
    raw = raw if isinstance(raw, dict) else {}
    parties_raw = raw.get("parties") if isinstance(raw.get("parties"), dict) else {}
    parties = {}
    for party_id in PARTY_IDS:
        party_raw = parties_raw.get(party_id) if isinstance(parties_raw.get(party_id), dict) else {}
        base_party = base["parties"][party_id]
        language = party_raw.get("language")
        parties[party_id] = {
            "name": clean_label(party_raw.get("name"), base_party["name"], MAX_NAME_CHARS),
            "language": language if language in LANGUAGES else base_party["language"],
        }
    return {"meeting": clean_label(raw.get("meeting"), base["meeting"], MAX_MEETING_CHARS), "parties": parties}


def other_party(party_id):
    """The listener: 'B' when A speaks, 'A' when B speaks."""
    return "B" if party_id == "A" else "A"


def now_iso():
    """The current time in UTC as ISO 8601 text, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_utterance_id(meeting, timestamp, position, speaker, transcript):
    """Same sentence in the same meeting always gets the same id, so re-reading a file
    never duplicates it. `position` (a line number) tells apart repeated sentences."""
    key = "|".join([meeting, timestamp, str(position), speaker, transcript])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def make_utterance(setup, speaker, transcript, timestamp=None, input_type="text", position=""):
    """Build one raw sentence record. Returns (record, None) or (None, error_message).

    timestamp=None means "now" (live input). An unreadable timestamp is stored as ''.
    The sentence is translated towards the other party, so the listener's language
    becomes the target language.
    """
    speaker = speaker.strip().upper() if isinstance(speaker, str) else ""
    if speaker not in PARTY_IDS:
        return None, "speaker must be A or B"
    if not isinstance(transcript, str) or not transcript.strip():
        return None, "missing or empty sentence"
    text = transcript.strip()
    if len(text) > MAX_SENTENCE_CHARS:
        return None, "sentence longer than %d characters" % MAX_SENTENCE_CHARS
    when = now_iso() if timestamp is None else valid_timestamp(timestamp)
    me, listener = setup["parties"][speaker], setup["parties"][other_party(speaker)]
    return {
        "id": make_utterance_id(setup["meeting"], when, position, speaker, text),
        "meeting": setup["meeting"],
        "timestamp": when,
        "speaker": speaker,
        "speaker_name": me["name"],
        "speaker_language": me["language"],
        "listener_name": listener["name"],
        "target_language": listener["language"],
        "transcript": text,
        "input_type": input_type,
    }, None


# ---------- reading meeting files ----------

# "A: text", "b: text" or "[2026-10-14T09:00:05+08:00] B: text" (a full-width colon also works)
TEXT_LINE = re.compile(r"^\s*(?:\[(?P<time>[^\]]*)\]\s*)?(?P<speaker>[AaBb])\s*[:：]\s*(?P<text>.*\S)\s*$")


def parse_meeting_content(name, content, setup):
    """Parse a meeting file. Returns (records, errors). Never raises.

    .json  an object {"meeting": ..., "parties": {"A": {"name", "language"}, "B": {...}},
           "utterances": [{"speaker": "A", "timestamp": "...", "transcript": "..."}]}
           or just the list of utterances (then `setup` supplies the parties).
    .txt   one sentence per line:  A: text   or   [2026-10-14T09:00:05+08:00] B: text
    """
    records, errors = [], []
    short_name = os.path.basename(name)
    items = []  # (position, speaker, timestamp, transcript)

    if name.lower().endswith(".json"):
        try:
            data = json.loads(content)
        except ValueError as error:
            return [], ["%s is not valid JSON: %s" % (short_name, error)]
        if isinstance(data, dict):
            setup = normalise_setup(data, setup)
            data = data.get("utterances")
        if not isinstance(data, list):
            return [], ["%s must contain a list of utterances (or an object with an 'utterances' list)" % short_name]
        for position, item in enumerate(data, start=1):
            if isinstance(item, dict):
                items.append((position, item.get("speaker"), item.get("timestamp", ""), item.get("transcript")))
            else:
                errors.append("%s item %d skipped: not an object" % (short_name, position))
    else:
        for position, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            match = TEXT_LINE.match(line)
            if match is None:
                errors.append("%s line %d skipped: expected 'A: text' or 'B: text'" % (short_name, position))
            else:
                items.append((position, match.group("speaker"), match.group("time") or "", match.group("text")))

    for position, speaker, timestamp, transcript in items:
        record, problem = make_utterance(setup, speaker, transcript, timestamp or "", "file", position)
        if problem:
            errors.append("%s item %d skipped: %s" % (short_name, position, problem))
        else:
            records.append(record)
    return records, errors


def read_meeting_file(path, setup):
    """Read a meeting file from disk. Returns (records, errors). Never raises."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            content = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        return [], ["cannot read %s: %s" % (path, error)]
    return parse_meeting_content(path, content, setup)


# ---------- time ----------

def format_clock(timestamp, tz_name=None, with_date=False):
    """'14:32:05' (or with the date) in the given IANA time zone; the computer's own zone
    if tz_name is None. Naive times are taken as UTC. Unreadable times show '--:--:--'."""
    try:
        moment = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return "--:--:--"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        moment = moment.astimezone(ZoneInfo(tz_name)) if tz_name else moment.astimezone()
    except (KeyError, ValueError, OSError):
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S")


# ---------- formatting (terminal) ----------

def direction_text(record):
    """'Acme (English) -> Mitra (Indonesian)': who is speaking to whom, in which languages."""
    return "%s (%s) -> %s (%s)" % (record.get("speaker_name", "?"), record.get("speaker_language", "?"),
                                    record.get("listener_name", "?"), record.get("target_language", "?"))


def format_sentence(record, tz_name=None):
    """Detailed multi-line view of one sentence."""
    lines = [
        "[%s] %s  [%s]" % (format_clock(record.get("timestamp"), tz_name), direction_text(record),
                           record.get("outcome", "?")),
        "    Said       : %s" % record.get("transcript", ""),
        "    Translated : %s" % record.get("translation", ""),
        "    Tone       : %s (confidence %.2f), intensity %s/5" % (
            record.get("tone", "?"), record.get("tone_confidence", 0), record.get("intensity", "?")),
        "    Note       : %s" % "; ".join(record.get("reasons", [])),
    ]
    return "\n".join(lines)


def format_short_sentence(record, tz_name=None):
    """Compact two-line view used for the 'previous sentences' list."""
    return "[%s] %s (%s): %s\n           -> %s" % (
        format_clock(record.get("timestamp"), tz_name), record.get("speaker_name", "?"),
        record.get("speaker_language", "?"), record.get("transcript", ""), record.get("translation", ""))


def format_conversation(latest, previous, tz_name=None):
    """The latest sentence in full, then the previous sentences in short form."""
    if latest is None:
        return "Nothing has been said in this meeting yet."
    lines = ["--- Latest translation ---", format_sentence(latest, tz_name),
             "\n--- Previous %d sentences ---" % len(previous) if previous else "\n(no earlier sentences)"]
    lines.extend(format_short_sentence(record, tz_name) for record in previous)
    return "\n".join(lines)


def count_by(records, key):
    """{value: how many records have it} for one field, e.g. count_by(records, "tone")."""
    counts = {}
    for record in records:
        value = record.get(key, "?")
        counts[value] = counts.get(value, 0) + 1
    return counts


def format_transcript(records, tz_name=None):
    if not records:
        return "No sentences."
    return "\n".join(format_short_sentence(record, tz_name) for record in records)


def format_summary(records):
    if not records:
        return "No records yet."
    lines = ["Total sentences: %d" % len(records)]
    for title, key in (("By outcome", "outcome"), ("By speaker", "speaker_name"),
                       ("By language spoken", "detected_language"), ("By tone", "tone")):
        counts = count_by(records, key)
        parts = ", ".join("%s=%d" % (name, counts[name]) for name in sorted(counts))
        lines.append("%s: %s" % (title, parts))
    return "\n".join(lines)
