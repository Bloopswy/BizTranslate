"""Tests for the io_manager display functions (clock, sentence formatting, summary, exports).

Plain functions only (no classes, per the 100% procedural constraint).
Run from the Project folder:  python tests/test_io_display.py
No network, API key, Streamlit or Whisper install needed.
"""

import contextlib
import csv
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io_manager


# ---------------------------------------------------------------- helpers

def test_setup():
    return io_manager.normalise_setup({
        "meeting": "m1",
        "parties": {"A": {"name": "Acme", "language": "English"}, "B": {"name": "Mitra", "language": "Indonesian"}},
    })


def good_ai(**overrides):
    fields = {
        "detected_language": "English", "language_confidence": 0.95,
        "translation": "Selamat pagi", "translation_confidence": 0.9,
        "tone": "neutral", "tone_confidence": 0.9, "intensity": 2,
        "tone_reason": "Tenang.",
    }
    fields.update(overrides)
    return fields


def saved(seq, text="hi", speaker="A", **extra):
    """A fully processed record, as stored in records.json."""
    record, problem = io_manager.make_utterance(
        test_setup(), speaker, text, "2026-10-14T09:%02d:00+00:00" % seq, "text", seq)
    assert problem is None, problem
    record.update(good_ai())
    record.update({"seq": seq, "outcome": "ACCEPT", "reasons": ["clear and routine"]})
    record.update(extra)
    return record


def printed(fn, *args):
    """What fn(*args) prints to the terminal."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        fn(*args)
    return buffer.getvalue()


# ---------------------------------------------------------------- time

def test_format_clock_converts_time_zones_and_never_crashes():
    stamp = "2026-10-14T09:00:05+08:00"
    assert io_manager.format_clock(stamp, "UTC") == "01:00:05"
    assert io_manager.format_clock(stamp, "Asia/Singapore") == "09:00:05"
    assert io_manager.format_clock(stamp, "Asia/Jakarta") == "08:00:05"
    assert io_manager.format_clock(stamp, "UTC", with_date=True) == "2026-10-14 01:00:05"
    assert io_manager.format_clock("2026-10-14T09:00:05", "UTC") == "09:00:05", "naive times are taken as UTC"
    assert io_manager.format_clock("", "UTC") == "--:--:--" and io_manager.format_clock(None, "UTC") == "--:--:--"
    assert io_manager.format_clock("not a time", "UTC") == "--:--:--"
    assert io_manager.format_clock(stamp, "Not/AZone") == "01:00:05", "unknown zone falls back to UTC"
    assert len(io_manager.format_clock(stamp)) == 8, "no zone given: the computer's own zone"


def test_format_clock_crosses_midnight_into_the_next_day():
    assert io_manager.format_clock("2026-10-14T23:30:00+00:00", "Asia/Singapore", with_date=True) == "2026-10-15 07:30:00"


# ---------------------------------------------------------------- formatting

def test_format_sentence_shows_direction_translation_tone_and_note():
    text = io_manager.format_sentence(saved(1, "Good morning", tone="angry", tone_confidence=0.81, intensity=4,
                                            outcome="TENSION", reasons=["angry tone", "low confidence"]), "UTC")
    assert text.splitlines()[0] == "[09:01:00] Acme (English) -> Mitra (Indonesian)  [TENSION]"
    assert "Said       : Good morning" in text and "Translated : Selamat pagi" in text
    assert "angry (confidence 0.81), intensity 4/5" in text
    assert "Note       : angry tone; low confidence" in text


def test_format_sentence_handles_a_record_not_yet_translated():
    raw = io_manager.make_utterance(test_setup(), "B", "Halo", "")[0]
    text = io_manager.format_sentence(raw, "UTC")
    assert "[--:--:--]" in text and "[?]" in text and "Mitra (Indonesian) -> Acme (English)" in text


def test_format_short_sentence_is_two_lines():
    lines = io_manager.format_short_sentence(saved(2, "Hello"), "UTC").splitlines()
    assert lines == ["[09:02:00] Acme (English): Hello", "           -> Selamat pagi"]


def test_terminal_conversation_shows_latest_and_previous_with_times():
    rows = [saved(1, "First"), saved(2, "Second"), saved(3, "Third")]
    text = io_manager.format_conversation(rows[-1], rows[:-1], "UTC")
    assert "Latest translation" in text and "Previous 2 sentences" in text
    assert "[09:03:00]" in text and "[09:01:00]" in text and "[09:02:00]" in text
    assert text.index("Third") < text.index("First"), "the latest sentence comes first"
    assert "Nothing has been said" in io_manager.format_conversation(None, [])
    assert "no earlier sentences" in io_manager.format_conversation(rows[0], [])


def test_count_by_transcript_and_summary():
    rows = [saved(1, "First"), saved(2, "Second", speaker="B", tone="happy"), saved(3, "Third")]
    assert io_manager.count_by(rows, "speaker_name") == {"Acme": 2, "Mitra": 1}
    assert io_manager.count_by(rows, "missing_key") == {"?": 3}
    assert io_manager.count_by([], "tone") == {}
    assert io_manager.format_transcript([], "UTC") == "No sentences."
    assert len(io_manager.format_transcript(rows, "UTC").splitlines()) == 6
    summary = io_manager.format_summary(rows)
    assert "Total sentences: 3" in summary and "By speaker: Acme=2, Mitra=1" in summary
    assert "By tone: happy=1, neutral=2" in summary and "By outcome: ACCEPT=3" in summary
    assert io_manager.format_summary([]) == "No records yet."


def test_show_functions_print_the_formatted_text():
    rows = [saved(1, "First"), saved(2, "Second")]
    assert printed(io_manager.show_message, "hello") == "hello\n"
    assert printed(io_manager.show_error, "bad input") == "Error: bad input\n"
    assert printed(io_manager.show_sentence, rows[0], "UTC") == io_manager.format_sentence(rows[0], "UTC") + "\n"
    assert printed(io_manager.show_conversation, rows[1], rows[:1], "UTC") == \
        io_manager.format_conversation(rows[1], rows[:1], "UTC") + "\n"
    assert printed(io_manager.show_transcript, rows, "UTC") == io_manager.format_transcript(rows, "UTC") + "\n"
    assert printed(io_manager.show_summary, rows) == io_manager.format_summary(rows) + "\n"


# ---------------------------------------------------------------- exports

def test_exports():
    rows = [saved(1, "Hello, \"friend\"", speaker="A"), saved(2, "Halo", speaker="B")]
    csv_text = io_manager.records_to_csv(rows)
    lines = csv_text.splitlines()
    assert lines[0].startswith("meeting,seq,timestamp,speaker_name") and len(lines) == 3
    assert "clear and routine" in csv_text and '"Hello, ""friend"""' in csv_text
    minutes = io_manager.records_to_text(rows, "UTC")
    assert "[2026-10-14 09:01:00]" in minutes and "Acme (English) -> Mitra (Indonesian)" in minutes
    assert "Translation: Selamat pagi" in minutes
    assert io_manager.records_to_text([]) == ""
    assert io_manager.safe_filename("Q4 plan / Acme & Mitra!") == "Q4_plan_Acme_Mitra"
    assert io_manager.safe_filename("///") == "meeting"


def test_csv_round_trips_and_keeps_chinese_text():
    rows = [saved(1, "你好", reasons=["one", "two"], extra_field="ignored")]
    parsed = list(csv.DictReader(io.StringIO(io_manager.records_to_csv(rows))))
    assert parsed[0]["transcript"] == "你好" and parsed[0]["reasons"] == "one; two"
    assert list(parsed[0]) == io_manager.CSV_COLUMNS, "unknown fields are left out"
    assert io_manager.records_to_csv([]).strip() == ",".join(io_manager.CSV_COLUMNS)


# ---------------------------------------------------------------- runner

def run_all():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and name != "test_setup" and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            io_manager.show_message("PASS  " + name)
        except AssertionError as error:
            failures += 1
            io_manager.show_message("FAIL  %s %s" % (name, error))
        except Exception as error:  # noqa: BLE001 - report any crash as a failure
            failures += 1
            io_manager.show_message("ERROR %s: %r" % (name, error))
    io_manager.show_message("\n%d tests, %d failed" % (len(tests), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_all())
