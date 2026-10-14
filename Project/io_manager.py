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
