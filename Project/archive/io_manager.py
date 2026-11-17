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


# ---------- basic output ----------

def show_message(text):
    print(text)


def show_error(text):
    print("Error: " + text)


# ---------- validated prompts (terminal) ----------

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


def prompt_speaker(setup):
    """Returns 'A' or 'B', or None if input ended."""
    show_message("Who is speaking?  1) %s   2) %s" % (describe_party(setup, "A"), describe_party(setup, "B")))
    choice = prompt_choice("Speaker 1-2: ", ["1", "2"])
    return None if choice is None else PARTY_IDS[int(choice) - 1]


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


def prompt_language_or_keep(label, current):
    show_message("%s: 1) English  2) Indonesian  3) Chinese  (Enter keeps %s)" % (label, current))
    choice = prompt_choice("Choice: ", ["", "1", "2", "3"])
    if choice is None:
        return None
    return current if choice == "" else LANGUAGES[int(choice) - 1]


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


# ---------- configuration ----------

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


# ---------- meeting setup and sentence records ----------

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_meeting_name():
    return "meeting-" + datetime.now().strftime("%Y-%m-%d")


def clean_label(text, fallback, limit):
    """A short single-line label (names are put into prompts, so keep them tidy)."""
    if not isinstance(text, str):
        return fallback
    cleaned = " ".join(text.split())
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())[:limit].strip()
    return cleaned or fallback


def default_setup():
    return {
        "meeting": default_meeting_name(),
        "parties": {
            "A": {"name": "Party A", "language": "English"},
            "B": {"name": "Party B", "language": "Indonesian"},
        },
    }


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
    return "B" if party_id == "A" else "A"


def valid_timestamp(value):
    """The timestamp text if it is a valid ISO 8601 time, else ''."""
    if not isinstance(value, str):
        return ""
    try:
        datetime.fromisoformat(value.strip())
    except ValueError:
        return ""
    return value.strip()


def make_utterance_id(meeting, timestamp, position, speaker, transcript):
    """Same sentence in the same meeting always gets the same id, so re-reading a file
    never duplicates it. `position` (a line number) tells apart repeated sentences."""
    key = "|".join([meeting, timestamp, str(position), speaker, transcript])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def make_utterance(setup, speaker, transcript, timestamp=None, input_type="text", position=""):
    """Build one raw sentence record. Returns (record, None) or (None, error_message).

    timestamp=None means "now" (live input). An unreadable timestamp is stored as ''.
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

TEXT_LINE = re.compile(r"^\s*(?:\[(?P<time>[^\]]*)\]\s*)?(?P<speaker>[AaBb])\s*[:\uFF1A]\s*(?P<text>.*\S)\s*$")


def list_input_files(folder=INPUT_DIR):
    """Names of .json / .txt files in the input folder (sorted)."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(n for n in names if n.lower().endswith((".json", ".txt")))


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


# ---------- speech to text (runs locally; the AI never receives audio) ----------

_speech_models = {}  # module-level cache so the model loads once per process


def get_speech_model():
    """Load (once) the local Whisper model. Raises ImportError if not installed."""
    if "model" not in _speech_models:
        from faster_whisper import WhisperModel
        _speech_models["model"] = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
    return _speech_models["model"]


def pick_supported_language(language_probabilities):
    """From Whisper's (code, probability) pairs choose the likeliest of English,
    Chinese or Indonesian. Returns a short code like 'id', or None."""
    best_code, best_probability = None, -1.0
    for code, probability in language_probabilities or []:
        if code in WHISPER_TO_SPEECH_CODE and probability > best_probability:
            best_code, best_probability = code, probability
    return best_code


def run_transcription(model, audio_bytes, language):
    """One Whisper pass. Returns (text, info). Must consume the segment generator."""
    segments, info = model.transcribe(
        io.BytesIO(audio_bytes), language=language, beam_size=5, temperature=0.0, vad_filter=True
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return text, info


def transcribe_audio(audio_bytes, speech_code=None):
    """Turn a recording into text.

    speech_code is 'en-US', 'zh-CN', 'id-ID' or None for auto-detect (restricted to those three).
    Returns (text, speech_code_used_or_None, error_or_None). Never raises.
    """
    try:
        model = get_speech_model()
    except ImportError:
        return "", None, "Speech-to-text is not installed. Run: pip install faster-whisper"
    except Exception as error:  # noqa: BLE001 - e.g. model download failed
        return "", None, "Could not load the speech model (%s). The first run needs internet to download it." % error

    try:
        language = SPEECH_CODE_TO_WHISPER.get(speech_code)
        text, info = run_transcription(model, audio_bytes, language)
        used = language or getattr(info, "language", None)
        if language is None:
            best = pick_supported_language(getattr(info, "all_language_probs", None))
            if best is not None and best != used:  # e.g. Whisper said Malay, we only support Indonesian
                text, info = run_transcription(model, audio_bytes, best)
                used = best
        return text, WHISPER_TO_SPEECH_CODE.get(used), None
    except Exception as error:  # noqa: BLE001 - bad/corrupt audio etc.
        return "", None, "Could not transcribe that recording (%s)." % error


# ---------- formatting (terminal) ----------

def count_by(records, key):
    counts = {}
    for record in records:
        value = record.get(key, "?")
        counts[value] = counts.get(value, 0) + 1
    return counts


def direction_text(record):
    return "%s (%s) -> %s (%s)" % (record.get("speaker_name", "?"), record.get("speaker_language", "?"),
                                    record.get("listener_name", "?"), record.get("target_language", "?"))


def format_sentence(record, tz_name=None):
    """Detailed multi-line view of one sentence."""
    lines = [
        "[%s] %s  [%s]" % (format_clock(record.get("timestamp"), tz_name), direction_text(record),
                           record.get("outcome", "?")),
        "    Said       : %s" % record.get("transcript", ""),
        "    Translated : %s" % record.get("translation", ""),
        "    Tone       : %s (confidence %.2f), intensity %s/5, attention score %s/100" % (
            record.get("tone", "?"), record.get("tone_confidence", 0), record.get("intensity", "?"),
            record.get("score", "-")),
        "    Note       : %s" % "; ".join(record.get("reasons", [])),
    ]
    return "\n".join(lines)


def format_short_sentence(record, tz_name=None):
    """Compact two-line view used for the 'previous sentences' list."""
    return "[%s] %s (%s): %s\n           -> %s" % (
        format_clock(record.get("timestamp"), tz_name), record.get("speaker_name", "?"),
        record.get("speaker_language", "?"), record.get("transcript", ""), record.get("translation", ""))


def format_conversation(latest, previous, tz_name=None):
    if latest is None:
        return "Nothing has been said in this meeting yet."
    lines = ["--- Latest translation ---", format_sentence(latest, tz_name),
             "\n--- Previous %d sentences ---" % len(previous) if previous else "\n(no earlier sentences)"]
    lines.extend(format_short_sentence(record, tz_name) for record in previous)
    return "\n".join(lines)


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


def show_conversation(latest, previous, tz_name=None):
    show_message(format_conversation(latest, previous, tz_name))


def show_sentence(record, tz_name=None):
    show_message(format_sentence(record, tz_name))


def show_transcript(records, tz_name=None):
    show_message(format_transcript(records, tz_name))


def show_summary(records):
    show_message(format_summary(records))


# ---------- exports (used by the web app's download buttons) ----------

CSV_COLUMNS = [
    "meeting", "seq", "timestamp", "speaker_name", "speaker_language", "listener_name", "target_language",
    "transcript", "translation", "detected_language", "language_confidence", "translation_confidence",
    "tone", "tone_confidence", "intensity", "score", "tone_reason", "outcome", "reasons", "input_type", "id",
]


def safe_filename(text):
    """A file-name-friendly version of a meeting name."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("._")
    return cleaned or "meeting"


def records_to_csv(records):
    """CSV text of the records (reasons joined with '; ')."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = dict(record)
        row["reasons"] = "; ".join(record.get("reasons", []))
        writer.writerow(row)
    return buffer.getvalue()


def records_to_text(records, tz_name=None):
    """Plain-text meeting minutes: one block per sentence with date and time."""
    blocks = []
    for record in records:
        blocks.append("[%s] %s\n  Said: %s\n  Translation: %s\n  Tone: %s\n  Flag: %s" % (
            format_clock(record.get("timestamp"), tz_name, with_date=True), direction_text(record),
            record.get("transcript", ""), record.get("translation", ""), record.get("tone", "?"),
            record.get("outcome", "?")))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


# ======================================================================
# Streamlit user interface (the web version of the same user boundary)
# ======================================================================

def _st():
    """Import Streamlit only when the web UI is used, so the terminal app and the
    tests do not need it installed."""
    import streamlit
    return streamlit


def escape_markdown(text):
    """Make arbitrary text safe to show with st.markdown ($5 must not become LaTeX, '1.' must
    not become a list, and so on)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>~$<])", r"\\\1", str(text))


def ui_configure_page():
    _st().set_page_config(page_title="Meeting Translator", page_icon="\U0001F310", layout="wide")


def ui_header():
    st = _st()
    st.title("Meeting Translator")
    st.caption(
        "A live interpreter for two parties speaking English, Indonesian or Chinese. Each sentence is "
        "translated into the other party's language, with its tone, and the last sentences stay on screen "
        "with timestamps."
    )


def _start_new_meeting():
    """Button callback: give the meeting a fresh name (a new meeting has no earlier sentences)."""
    _st().session_state["meeting_name"] = "meeting-" + datetime.now().strftime("%Y-%m-%d-%H%M")


def resolve_timezone(choice):
    """Turn the sidebar choice into an IANA zone name ('Auto' uses the browser's zone if known)."""
    if choice == AUTO_TIMEZONE:
        browser = getattr(getattr(_st(), "context", None), "timezone", None)
        return browser if isinstance(browser, str) and browser else "UTC"
    return choice if choice in TIMEZONE_CHOICES else "UTC"


def ui_sidebar(env_key, model_name, speech_model_name=""):
    """Meeting setup and settings. Returns (api_key, setup, time_zone_name)."""
    st = _st()
    with st.sidebar:
        st.header("Meeting setup")
        meeting = st.text_input("Meeting name", value=default_meeting_name(), key="meeting_name",
                                max_chars=MAX_MEETING_CHARS,
                                help="Sentences with the same meeting name belong together.")
        st.button("Start a new meeting", key="new_meeting", on_click=_start_new_meeting)
        parties = {}
        for party_id, default_language in (("A", "English"), ("B", "Indonesian")):
            st.markdown("**Party %s**" % party_id)
            name = st.text_input("Name of party %s" % party_id, value="Party %s" % party_id,
                                 key="name_%s" % party_id, max_chars=MAX_NAME_CHARS)
            language = st.selectbox("Language of party %s" % party_id, LANGUAGES,
                                    index=LANGUAGES.index(default_language), key="language_%s" % party_id)
            parties[party_id] = {"name": name, "language": language}
        setup = normalise_setup({"meeting": meeting, "parties": parties})
        if setup["parties"]["A"]["language"] == setup["parties"]["B"]["language"]:
            st.warning("Both parties use the same language, so sentences will only be tidied up, not translated.")
        zone_choice = st.selectbox("Time zone for timestamps", TIMEZONE_CHOICES, key="timezone_choice")

        st.header("Settings")
        api_key = env_key
        if env_key:
            st.success("API key loaded from the environment.")
        else:
            api_key = st.text_input("Google AI Studio API key", type="password",
                                    help="Get one at aistudio.google.com/apikey. It is kept in memory only.")
        st.write("AI model: `%s`" % model_name)
        if speech_model_name:
            st.write("Speech model: `whisper-%s`" % speech_model_name)
    return api_key.strip(), setup, resolve_timezone(zone_choice)


def ui_message(kind, text):
    """kind is one of: success, error, warning, info."""
    st = _st()
    {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(text)


def ui_progress_start(text):
    return _st().progress(0.0, text=text)


def ui_progress_update(bar, fraction, text):
    bar.progress(min(max(fraction, 0.0), 1.0), text=text)


def ui_progress_clear(bar):
    bar.empty()


def ui_main_tabs():
    """The three top-level tabs. Returns (live_tab, transcript_tab, filter_tab)."""
    return _st().tabs(["Live", "Transcript", "Filter"])


def _queue_submission(kind):
    """Button callback for 'Translate'. Moves the text out of its box into a pending slot (so the
    box is empty for the next sentence) and stamps the time the sentence was submitted."""
    st = _st()
    key = "voice_transcript" if kind == "voice" else "text_message"
    st.session_state["pending_utterance"] = {
        "kind": kind, "text": st.session_state.get(key, "") or "", "timestamp": now_iso(),
    }
    if kind == "voice":
        st.session_state.pop("voice_transcript", None)
        st.session_state["voice_counter"] = st.session_state.get("voice_counter", 0) + 1  # fresh recorder
    else:
        st.session_state["text_message"] = ""


def ui_live_input(setup):
    """Who is speaking, plus the ways to give a sentence. Returns the list of sentence records
    submitted on this interaction (empty if the user did nothing)."""
    st = _st()
    submitted = []

    labels = {party_id: describe_party(setup, party_id) for party_id in PARTY_IDS}
    chosen = st.radio("Who is speaking?", PARTY_IDS, format_func=lambda party_id: labels[party_id],
                      horizontal=True, key="speaker")
    speaker = chosen if chosen in PARTY_IDS else "A"
    listener = other_party(speaker)
    party = setup["parties"][speaker]
    st.caption("%s speaks %s; it will be translated into %s for %s." % (
        party["name"], party["language"], setup["parties"][listener]["language"], setup["parties"][listener]["name"]))

    pending = st.session_state.pop("pending_utterance", None)

    tab_voice, tab_text, tab_file, tab_html = st.tabs(
        ["Record voice", "Type text", "Upload meeting file", "Browser transcription (HTML)"]
    )

    with tab_voice:
        st.write("**1.** Record  **2.** Transcribe  **3.** Check the text, then translate. "
                 "Only the text is sent to the AI, never the audio.")
        audio = st.audio_input("Record %s" % party["name"], key="voice_audio_%d" % st.session_state.get("voice_counter", 0))
        if audio is not None and st.button("Transcribe", key="voice_transcribe"):
            data = audio.getvalue()
            if not data:
                ui_message("error", "The recording is empty. Record again.")
            elif len(data) > MAX_AUDIO_BYTES:
                ui_message("error", "The recording is larger than %d MB. Record a shorter sentence."
                           % (MAX_AUDIO_BYTES // (1024 * 1024)))
            else:
                with st.spinner("Transcribing... (the first run downloads the speech model)"):
                    text, _code, error = transcribe_audio(data, LANGUAGE_TO_SPEECH_CODE[party["language"]])
                if error:
                    ui_message("error", error)
                elif not text:
                    ui_message("warning", "No speech was detected. Check your microphone and record again.")
                else:
                    st.session_state["voice_transcript"] = text  # set before the text box is created
        if "voice_transcript" in st.session_state:
            st.text_area("Transcript (fix any mistakes before translating)", key="voice_transcript",
                         max_chars=MAX_SENTENCE_CHARS, height=120)
            st.button("Translate", type="primary", key="voice_translate",
                      on_click=_queue_submission, args=("voice",))

    with tab_text:
        st.text_area("Sentence", key="text_message", max_chars=MAX_SENTENCE_CHARS, height=100,
                     placeholder="Type what %s says" % party["name"])
        st.button("Translate", type="primary", key="text_translate",
                  on_click=_queue_submission, args=("text",))

    with tab_file:
        st.write("Upload a meeting file: `.json` (see the README) or `.txt` with lines like `A: Good morning` "
                 "or `[2026-10-14T09:00:05+08:00] B: Selamat pagi`.")
        files = st.file_uploader("Meeting files", type=["json", "txt"], accept_multiple_files=True,
                                 key="uploaded_files")
        if files and st.button("Translate file(s)", type="primary", key="translate_files"):
            seen = set()
            for uploaded in files:
                try:
                    content = uploaded.getvalue().decode("utf-8-sig")
                except UnicodeDecodeError:
                    ui_message("error", "%s is not a UTF-8 text file." % uploaded.name)
                    continue
                found, errors = parse_meeting_content(uploaded.name, content, setup)
                for message in errors:
                    ui_message("warning", message)
                for record in found:
                    if record["id"] not in seen:
                        seen.add(record["id"])
                        submitted.append(record)

    with tab_html:
        st.write("Use your browser's own speech recognition (Chrome or Edge). Choose the speaker, add sentences "
                 "to the list, download the file, then upload it in the **Upload meeting file** tab.")
        try:
            with open(RECORDER_PATH, "r", encoding="utf-8") as handle:
                page = handle.read()
            import streamlit.components.v1 as components
            components.html(page, height=900, scrolling=True)
        except OSError as error:
            ui_message("error", "Could not load the recorder page: %s" % error)

    if pending:
        record, problem = make_utterance(setup, speaker, pending["text"], pending["timestamp"], pending["kind"])
        if problem:
            ui_message("error", "Nothing to translate (%s). Type or record a sentence first." % problem)
        else:
            submitted.append(record)
    return submitted


def ui_run_summary(counts):
    parts = "%(processed)d translated, %(skipped)d already done, %(failed)d failed" % counts
    if counts["failed"]:
        ui_message("warning", parts + ". Failed sentences were not saved; check your API key and try again.")
    elif counts["processed"]:
        ui_message("success", parts + ".")
    else:
        ui_message("info", parts + ".")


def ui_sentence(record, tz_name, show_meeting=False):
    """One sentence: time, speaker, what was said and the translation."""
    st = _st()
    header = "`%s` **%s** (%s) %s" % (format_clock(record.get("timestamp"), tz_name),
                                      escape_markdown(record.get("speaker_name", "?")),
                                      escape_markdown(record.get("speaker_language", "?")),
                                      OUTCOME_ICONS.get(record.get("outcome"), ""))
    if show_meeting:
        header += " \u00B7 _%s_" % escape_markdown(record.get("meeting", "?"))
    st.markdown("%s  \n%s  \n\u21B3 %s" % (header, escape_markdown(record.get("transcript", "")),
                                          escape_markdown(record.get("translation", ""))))
    detail = "Tone: %s (%.0f%%), intensity %s/5" % (record.get("tone", "?"), record.get("tone_confidence", 0) * 100,
                                                    record.get("intensity", "?"))
    if "score" in record:
        detail += ", attention score %s/100" % record["score"]
    if record.get("outcome") not in (None, "ACCEPT") and record.get("reasons"):
        detail += " \u00B7 " + "; ".join(record["reasons"])
    st.caption(detail)


def ui_conversation_panel(latest, previous, tz_name, context_count):
    """The newest translation, big, then the sentences before it, each with a timestamp."""
    st = _st()
    st.subheader("Latest translation")
    if latest is None:
        st.info("Nothing has been said in this meeting yet. Pick who is speaking, then record or type a sentence.")
        return
    with st.container(border=True):
        st.caption("%s  |  %s" % (format_clock(latest.get("timestamp"), tz_name), direction_text(latest).replace("->", "\u2192")))
        st.markdown("**Said:** " + escape_markdown(latest.get("transcript", "")))
        st.markdown("### " + escape_markdown(latest.get("translation", "")))
        st.caption("Tone: %s (%.0f%%), intensity %s/5 \u00B7 %s" % (
            latest.get("tone", "?"), latest.get("tone_confidence", 0) * 100, latest.get("intensity", "?"),
            latest.get("tone_reason", "")))
        reasons = "; ".join(latest.get("reasons", []))
        outcome = latest.get("outcome")
        if outcome == "TENSION":
            ui_message("warning", "Tense moment: %s. Consider slowing down and confirming that both sides understand." % reasons)
        elif outcome == "CHECK":
            ui_message("info", "Please confirm this translation with the speaker: %s." % reasons)
        elif outcome == "REJECT":
            ui_message("error", "This sentence could not be translated: %s." % reasons)

    st.subheader("Previous %d sentences" % context_count)
    if not previous:
        st.caption("No earlier sentences yet.")
    for record in previous:
        ui_sentence(record, tz_name)


def ui_meeting_picker(meetings, current):
    """Choose which meeting the Transcript tab shows (defaults to the current one)."""
    options = list(meetings)
    if current not in options:
        options = [current] + options
    chosen = _st().selectbox("Meeting", options, index=options.index(current), key="transcript_meeting_" + current)
    return chosen if chosen in options else current


def ui_overview(records):
    st = _st()
    if not records:
        st.info("No sentences yet.")
        return
    outcome_counts = count_by(records, "outcome")
    columns = st.columns(5)
    columns[0].metric("Sentences", len(records))
    for column, name in zip(columns[1:], OUTCOME_ORDER):
        column.metric("%s %s" % (OUTCOME_ICONS[name], name.title()), outcome_counts.get(name, 0))

    tone_counts = count_by(records, "tone")
    language_counts = count_by(records, "detected_language")
    import pandas as pd
    left, right = st.columns(2)
    left.caption("Sentences by tone")
    left.bar_chart(pd.Series({t: tone_counts[t] for t in TONE_ORDER if t in tone_counts}))
    right.caption("Sentences by language spoken")
    right.bar_chart(pd.Series(language_counts))


def ui_transcript(records, tz_name, show_meeting=False):
    st = _st()
    if not records:
        st.write("No sentences to show.")
        return
    for record in records:
        ui_sentence(record, tz_name, show_meeting)


def ui_downloads(records, tz_name=None, key_prefix="all", file_stem="meeting"):
    """Download buttons. key_prefix keeps widget ids unique when shown in more than one tab."""
    st = _st()
    if not records:
        return
    columns = st.columns([1, 1, 1, 3])
    columns[0].download_button("Download minutes (.txt)", records_to_text(records, tz_name),
                               file_name=file_stem + ".txt", mime="text/plain", key=key_prefix + "_txt")
    columns[1].download_button("Download JSON", json.dumps(records, ensure_ascii=False, indent=2),
                               file_name=file_stem + ".json", mime="application/json", key=key_prefix + "_json")
    columns[2].download_button("Download CSV", records_to_csv(records),
                               file_name=file_stem + ".csv", mime="text/csv", key=key_prefix + "_csv")


def ui_filter_tab(records):
    """Controls for the Filter tab. Returns keyword arguments for
    data_manager.filter_records_multi."""
    st = _st()
    st.write("Pick tones and/or languages (and/or a speaker). Leave a box empty to ignore it.")
    speakers = sorted({r.get("speaker_name") for r in records if r.get("speaker_name")})
    meetings = sorted({r.get("meeting") for r in records if r.get("meeting")})
    first, second, third, fourth = st.columns(4)
    tones = first.multiselect("Tone", TONE_ORDER, key="filter_tones")
    languages = second.multiselect("Language spoken", DETECTED_LANGUAGES, key="filter_languages")
    targets = third.multiselect("Translated into", LANGUAGES, key="filter_targets")
    names = fourth.multiselect("Speaker", speakers, key="filter_speakers")
    match_label = st.radio(
        "When more than one box is filled in, show sentences that match",
        ["All of them (AND)", "Any of them (OR)"], horizontal=True, key="filter_match",
    )
    with st.expander("More filters"):
        meeting = st.selectbox("Meeting", ["All meetings"] + meetings, key="filter_meeting")
        outcome = st.selectbox("Flag", ["All"] + OUTCOME_ORDER, key="filter_outcome")
    return {
        "tones": list(tones),
        "languages": list(languages),
        "target_languages": list(targets),
        "speakers": list(names),
        "match": "any" if match_label == "Any of them (OR)" else "all",
        "outcome": outcome if outcome in OUTCOME_ORDER else None,
        "meeting": meeting if meeting in meetings else None,
    }


def ui_filter_results(matched, total, tz_name):
    st = _st()
    st.metric("Matching sentences", "%d of %d" % (len(matched), total))
    ui_transcript(matched, tz_name, show_meeting=True)
    ui_downloads(matched, tz_name, key_prefix="filtered", file_stem="filtered_sentences")


def ui_subheader(text):
    _st().subheader(text)
