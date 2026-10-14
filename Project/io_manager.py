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