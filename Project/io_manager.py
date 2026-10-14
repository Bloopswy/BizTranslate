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

