"""Input/Output layer.

Every boundary between the system and the user lives here, including every
print() and input() call in the project. Also reads the transcript files that
the HTML recorder produces and normalises them into records.
"""

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone

INPUT_DIR = os.environ.get("INPUT_DIR", "input")
SPEECH_LANGUAGES = {"1": ("en-US", "English"), "2": ("zh-CN", "Chinese"), "3": ("id-ID", "Indonesian")}
MAX_TRANSCRIPT_CHARS = 2000
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # largest recording we will transcribe
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")  # tiny/base/small/medium: bigger = more accurate, slower
WHISPER_TO_SPEECH_CODE = {"en": "en-US", "zh": "zh-CN", "id": "id-ID"}
SPEECH_CODE_TO_WHISPER = {code: short for short, code in WHISPER_TO_SPEECH_CODE.items()}
RECORDER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "recorder.html")

MENU = (
    "\n=== Voice Triage ===\n"
    "1. Process transcript files from the input folder\n"
    "2. Type a transcript manually\n"
    "3. View all records\n"
    "4. Filter records\n"
    "5. Summary\n"
    "6. Quit"
)


# ---------- basic output ----------

def show_message(text):
    print(text)


def show_error(text):
    print("Error: " + text)


# ---------- validated prompts ----------

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
        show_error("please enter one of: " + ", ".join(valid_choices))


def prompt_menu():
    show_message(MENU)
    return prompt_choice("Choose 1-6: ", ["1", "2", "3", "4", "5", "6"])


def prompt_transcript():
    """Ask for a typed transcript. Returns {'selected_lang', 'transcript'} or None."""
    show_message("Language: 1) English  2) Chinese  3) Indonesian")
    choice = prompt_choice("Language 1-3: ", list(SPEECH_LANGUAGES))
    if choice is None:
        return None
    while True:
        text = ask("Transcript: ")
        if text is None:
            return None
        if not text:
            show_error("transcript cannot be empty")
        elif len(text) > MAX_TRANSCRIPT_CHARS:
            show_error("transcript is too long (max %d characters)" % MAX_TRANSCRIPT_CHARS)
        else:
            return {"selected_lang": SPEECH_LANGUAGES[choice][0], "transcript": text}


def prompt_filter():
    """Ask how to filter. Returns a dict of filter_records() keyword arguments, or None."""
    show_message("Filter by: 1) outcome  2) tone  3) language  4) minimum priority score")
    choice = prompt_choice("Filter 1-4: ", ["1", "2", "3", "4"])
    if choice is None:
        return None
    if choice == "1":
        value = prompt_choice("Outcome (ESCALATE/REVIEW/ACCEPT/REJECT): ",
                              ["ESCALATE", "REVIEW", "ACCEPT", "REJECT"])
        return None if value is None else {"outcome": value}
    if choice == "2":
        tones = ["neutral", "happy", "grateful", "sad", "anxious", "frustrated", "angry", "urgent"]
        value = prompt_choice("Tone (%s): " % "/".join(tones), tones)
        return None if value is None else {"tone": value}
    if choice == "3":
        value = prompt_choice("Language (English/Chinese/Indonesian): ",
                              ["English", "Chinese", "Indonesian"])
        return None if value is None else {"language": value}
    while True:
        text = ask("Minimum priority score (0-100): ")
        if text is None:
            return None
        if text.isdigit() and 0 <= int(text) <= 100:
            return {"min_priority": int(text)}
        show_error("enter a whole number from 0 to 100")


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


# ---------- reading input files ----------

def list_input_files(folder=INPUT_DIR):
    """Names of .json / .txt files in the input folder (sorted)."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(n for n in names if n.lower().endswith((".json", ".txt")))


def make_record_id(selected_lang, transcript):
    """Same transcript + language always gets the same id (so reruns are idempotent)."""
    digest = hashlib.sha1(("%s|%s" % (selected_lang, transcript)).encode("utf-8")).hexdigest()
    return digest[:12]


def normalise_input_record(item, fallback_timestamp=""):
    """Validate one raw item. Returns (record, None) or (None, error_message)."""
    if not isinstance(item, dict):
        return None, "item is not an object"
    transcript = item.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        return None, "missing or empty 'transcript'"
    transcript = transcript.strip()
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        return None, "transcript longer than %d characters" % MAX_TRANSCRIPT_CHARS
    selected_lang = item.get("selected_lang")
    if selected_lang not in [code for code, _ in SPEECH_LANGUAGES.values()]:
        selected_lang = None
    timestamp = item.get("timestamp") if isinstance(item.get("timestamp"), str) else fallback_timestamp
    return {
        "id": make_record_id(selected_lang, transcript),
        "timestamp": timestamp,
        "selected_lang": selected_lang,
        "transcript": transcript,
    }, None


def parse_input_content(name, content, fallback_timestamp=""):
    """Parse the text of a recorder .json file (list of items) or a .txt file (one
    transcript per line). Returns (records, errors). Never raises."""
    records, errors = [], []
    if name.lower().endswith(".json"):
        try:
            items = json.loads(content)
        except ValueError as error:
            return [], ["%s is not valid JSON: %s" % (name, error)]
        if not isinstance(items, list):
            return [], ["%s must contain a JSON list" % name]
    else:
        items = [{"transcript": line} for line in content.splitlines() if line.strip()]

    for position, item in enumerate(items, start=1):
        record, problem = normalise_input_record(item, fallback_timestamp)
        if problem:
            errors.append("%s item %d skipped: %s" % (os.path.basename(name), position, problem))
        else:
            records.append(record)
    return records, errors


def read_input_file(path):
    """Read an input file from disk. Returns (records, errors). Never raises."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        return [], ["cannot read %s: %s" % (path, error)]
    return parse_input_content(path, content)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_voice_record(transcript, selected_lang=None):
    """Build a raw record from a transcribed (and possibly user-corrected) voice message.
    Returns (record, None) or (None, error_message)."""
    record, problem = normalise_input_record(
        {"transcript": transcript, "selected_lang": selected_lang}, now_iso()
    )
    if record is not None:
        record["input_type"] = "voice"
    return record, problem


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


# ---------- formatting ----------

def format_record(record):
    """Multi-line, human-readable view of one record."""
    lines = [
        "[%s] %s  (priority %s)" % (record.get("outcome", "?"), record.get("id", "?"), record.get("priority_score", "?")),
        "  Original : %s" % record.get("transcript", ""),
        "  English  : %s" % record.get("english_translation", ""),
        "  Language : %s (confidence %.2f)" % (record.get("detected_language", "?"), record.get("language_confidence", 0)),
        "  Tone     : %s (confidence %.2f), urgency %s/5" % (record.get("tone", "?"), record.get("tone_confidence", 0), record.get("urgency", "?")),
        "  Why      : %s" % record.get("tone_reason", ""),
        "  Decision : %s" % "; ".join(record.get("reasons", [])),
    ]
    return "\n".join(lines)


def format_record_list(records):
    if not records:
        return "No records."
    ordered = sorted(records, key=lambda r: -r.get("priority_score", 0))
    return "\n\n".join(format_record(r) for r in ordered)


def count_by(records, key):
    counts = {}
    for record in records:
        value = record.get(key, "?")
        counts[value] = counts.get(value, 0) + 1
    return counts


def format_summary(records):
    if not records:
        return "No records yet."
    lines = ["Total records: %d" % len(records)]
    for title, key in (("By outcome", "outcome"), ("By language", "detected_language"), ("By tone", "tone")):
        counts = count_by(records, key)
        parts = ", ".join("%s=%d" % (name, counts[name]) for name in sorted(counts))
        lines.append("%s: %s" % (title, parts))
    return "\n".join(lines)


def show_records(records):
    show_message(format_record_list(records))


def show_summary(records):
    show_message(format_summary(records))


# ======================================================================
# Streamlit user interface (the web version of the same user boundary)
# ======================================================================

OUTCOME_ICONS = {"ESCALATE": "\U0001F534", "REVIEW": "\U0001F7E1", "ACCEPT": "\U0001F7E2", "REJECT": "\u26AA"}
OUTCOME_ORDER = ["ESCALATE", "REVIEW", "ACCEPT", "REJECT"]
TONE_ORDER = ["neutral", "happy", "grateful", "sad", "anxious", "frustrated", "angry", "urgent"]
LANGUAGE_CHOICES = {
    "Auto-detect": None,
    "English": "en-US",
    "Chinese": "zh-CN",
    "Indonesian": "id-ID",
}


def _st():
    """Import Streamlit only when the web UI is used, so the terminal app and the
    tests do not need it installed."""
    import streamlit
    return streamlit


def ui_configure_page():
    _st().set_page_config(page_title="Voice Triage", page_icon="\U0001F399", layout="wide")


def ui_header():
    st = _st()
    st.title("Voice Triage")
    st.caption(
        "Record or paste a message in English, Chinese or Indonesian. Speech is transcribed to text; "
        "the AI then reads the transcript, detects the language, translates it to English and reads "
        "the tone. Rules decide who should act first."
    )


def ui_sidebar(env_key, model_name, record_count, speech_model_name=""):
    """Show settings. Returns the API key to use ('' if none)."""
    st = _st()
    with st.sidebar:
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
        st.write("Saved records: **%d**" % record_count)
    return api_key.strip()


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


def ui_input_tabs():
    """Render the four ways to submit input. Returns a list of raw records
    submitted on this interaction (empty if the user did nothing)."""
    st = _st()
    submitted = []
    tab_voice, tab_html, tab_text, tab_file = st.tabs(
        ["Record voice", "Browser transcription (HTML)", "Type text", "Upload file"]
    )

    with tab_voice:
        st.write("**1.** Record  **2.** Transcribe  **3.** Check the text, then analyse. "
                 "Only the text is sent to the AI, never the audio.")
        audio = st.audio_input("Record a message", key="voice_audio")
        language = st.selectbox("Language spoken", list(LANGUAGE_CHOICES), key="voice_language")
        if audio is not None and st.button("Transcribe", key="voice_transcribe"):
            data = audio.getvalue()
            if not data:
                ui_message("error", "The recording is empty. Record again.")
            elif len(data) > MAX_AUDIO_BYTES:
                ui_message("error", "The recording is larger than %d MB. Record a shorter message."
                           % (MAX_AUDIO_BYTES // (1024 * 1024)))
            else:
                with st.spinner("Transcribing... (the first run downloads the speech model)"):
                    text, code, error = transcribe_audio(data, LANGUAGE_CHOICES[language])
                if error:
                    ui_message("error", error)
                elif not text:
                    ui_message("warning", "No speech was detected. Check your microphone and record again.")
                else:
                    st.session_state["voice_transcript"] = text  # set before the text box is created
                    st.session_state["voice_selected_lang"] = code
        if "voice_transcript" in st.session_state:
            st.text_area("Transcript (fix any mistakes before analysing)", key="voice_transcript",
                         max_chars=MAX_TRANSCRIPT_CHARS, height=140)
            if st.button("Analyse transcript", type="primary", key="voice_analyse"):
                record, problem = make_voice_record(st.session_state["voice_transcript"],
                                                    st.session_state.get("voice_selected_lang"))
                if problem:
                    ui_message("error", "The transcript cannot be analysed (%s)." % problem)
                else:
                    submitted.append(record)

    with tab_html:
        st.write("Use your browser's own speech recognition (Chrome or Edge). Add transcripts to the "
                 "list, download the file, then upload it in the **Upload file** tab.")
        try:
            with open(RECORDER_PATH, "r", encoding="utf-8") as handle:
                page = handle.read()
            import streamlit.components.v1 as components
            components.html(page, height=860, scrolling=True)
        except OSError as error:
            ui_message("error", "Could not load the recorder page: %s" % error)

    with tab_text:
        language = st.selectbox("Language", list(LANGUAGE_CHOICES), key="text_language")
        text = st.text_area("Message", max_chars=MAX_TRANSCRIPT_CHARS, height=140, key="text_message",
                            placeholder="Type or paste a message in English, Chinese or Indonesian")
        if st.button("Analyse text", type="primary", key="analyse_text"):
            record, problem = normalise_input_record(
                {"transcript": text, "selected_lang": LANGUAGE_CHOICES[language]}, now_iso()
            )
            if problem:
                ui_message("error", "Enter a message first (%s)." % problem)
            else:
                submitted.append(record)

    with tab_file:
        files = st.file_uploader("Transcript files (.json from the recorder, or .txt with one message per line)",
                                 type=["json", "txt"], accept_multiple_files=True, key="uploaded_files")
        if files and st.button("Analyse file(s)", type="primary", key="analyse_files"):
            seen = set()
            for uploaded in files:
                try:
                    content = uploaded.getvalue().decode("utf-8")
                except UnicodeDecodeError:
                    ui_message("error", "%s is not a UTF-8 text file." % uploaded.name)
                    continue
                found, errors = parse_input_content(uploaded.name, content, now_iso())
                for message in errors:
                    ui_message("warning", message)
                for record in found:
                    if record["id"] not in seen:
                        seen.add(record["id"])
                        submitted.append(record)
    return submitted


def ui_run_summary(counts):
    parts = "%(processed)d analysed, %(skipped)d already done, %(failed)d failed" % counts
    if counts["failed"]:
        ui_message("warning", parts + ". Failed items were not saved; check your API key and try again.")
    elif counts["processed"]:
        ui_message("success", parts + ".")
    else:
        ui_message("info", parts + ".")


def ui_filter_controls():
    """Sidebar-free filter row. Returns keyword arguments for data_manager.filter_records."""
    st = _st()
    columns = st.columns(4)
    outcome = columns[0].selectbox("Outcome", ["All"] + OUTCOME_ORDER)
    tone = columns[1].selectbox("Tone", ["All"] + TONE_ORDER)
    language = columns[2].selectbox("Language", ["All", "English", "Chinese", "Indonesian", "Other"])
    minimum = columns[3].slider("Minimum priority", 0, 100, 0)
    return {
        "outcome": None if outcome == "All" else outcome,
        "tone": None if tone == "All" else tone,
        "language": None if language == "All" else language,
        "min_priority": minimum if minimum > 0 else None,
    }


def ui_overview(records):
    st = _st()
    if not records:
        st.info("No records yet. Record or submit a message above to get started.")
        return
    outcome_counts = count_by(records, "outcome")
    columns = st.columns(5)
    columns[0].metric("Total", len(records))
    for column, name in zip(columns[1:], OUTCOME_ORDER):
        column.metric("%s %s" % (OUTCOME_ICONS[name], name.title()), outcome_counts.get(name, 0))

    tone_counts = count_by(records, "tone")
    language_counts = count_by(records, "detected_language")
    import pandas as pd
    left, right = st.columns(2)
    left.caption("Messages by tone")
    left.bar_chart(pd.Series({t: tone_counts.get(t, 0) for t in TONE_ORDER if t in tone_counts}))
    right.caption("Messages by language")
    right.bar_chart(pd.Series(language_counts))


def ui_record_cards(records):
    st = _st()
    if not records:
        st.write("No records match these filters.")
        return
    for record in sorted(records, key=lambda r: -r.get("priority_score", 0)):
        outcome = record.get("outcome", "?")
        preview = record.get("english_translation", "")
        if len(preview) > 90:
            preview = preview[:87] + "..."
        title = "%s %s  |  priority %s  |  %s" % (OUTCOME_ICONS.get(outcome, ""), outcome,
                                                 record.get("priority_score", "?"), preview)
        with st.expander(title):
            left, right = st.columns(2)
            left.markdown("**Original (%s)**" % record.get("detected_language", "?"))
            left.write(record.get("transcript", "") or "(no speech detected)")
            right.markdown("**English translation**")
            right.write(record.get("english_translation", ""))
            st.markdown(
                "**Tone:** %s (confidence %.0f%%)  \n**Urgency:** %s / 5  \n**Why:** %s  \n**Decision:** %s"
                % (record.get("tone", "?"), record.get("tone_confidence", 0) * 100,
                   record.get("urgency", "?"), record.get("tone_reason", ""),
                   "; ".join(record.get("reasons", [])))
            )
            st.caption("id %s | %s | %s input" % (record.get("id", "?"), record.get("timestamp", ""),
                                                 record.get("input_type", "text")))


def records_to_csv(records):
    """CSV text of all records (reasons joined with '; ')."""
    columns = ["id", "timestamp", "input_type", "outcome", "priority_score", "detected_language",
               "language_confidence", "tone", "tone_confidence", "urgency", "transcript",
               "english_translation", "tone_reason", "reasons"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = dict(record)
        row["reasons"] = "; ".join(record.get("reasons", []))
        writer.writerow(row)
    return buffer.getvalue()


def ui_downloads(records):
    st = _st()
    if not records:
        return
    left, right, _ = st.columns([1, 1, 4])
    left.download_button("Download JSON", json.dumps(records, ensure_ascii=False, indent=2),
                         file_name="records.json", mime="application/json")
    right.download_button("Download CSV", records_to_csv(records),
                          file_name="records.csv", mime="text/csv")


def ui_subheader(text):
    _st().subheader(text)
