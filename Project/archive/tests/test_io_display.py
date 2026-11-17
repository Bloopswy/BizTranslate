"""Tests for io_manager: display functions (time formatting, text formatting, exports)."""


import io_manager

from helpers import (saved)


def test_format_clock_converts_time_zones_and_never_crashes():
    stamp = "2026-10-14T09:00:05+08:00"
    assert io_manager.format_clock(stamp, "UTC") == "01:00:05"
    assert io_manager.format_clock(stamp, "Asia/Singapore") == "09:00:05"
    assert io_manager.format_clock(stamp, "Asia/Jakarta") == "08:00:05"
    assert io_manager.format_clock(stamp, "UTC", with_date=True) == "2026-10-14 01:00:05"
    assert io_manager.format_clock("2026-10-14T09:00:05", "UTC") == "09:00:05", "naive times are taken as UTC"
    assert io_manager.format_clock("", "UTC") == "--:--:--" and io_manager.format_clock(None, "UTC") == "--:--:--"
    assert io_manager.format_clock(stamp, "Not/AZone") == "01:00:05", "unknown zone falls back to UTC"
    assert len(io_manager.format_clock(stamp)) == 8, "no zone given: the computer's own zone"


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


def test_terminal_conversation_shows_latest_and_previous_with_times():
    rows = [saved(1, "First"), saved(2, "Second"), saved(3, "Third")]
    text = io_manager.format_conversation(rows[-1], rows[:-1], "UTC")
    assert "Latest translation" in text and "Previous 2 sentences" in text
    assert "[09:03:00]" in text and "[09:01:00]" in text and "[09:02:00]" in text
    assert "Nothing has been said" in io_manager.format_conversation(None, [])
    assert "no earlier sentences" in io_manager.format_conversation(rows[0], [])
    assert io_manager.format_transcript([], "UTC") == "No sentences."
    assert "By speaker: Acme=" in io_manager.format_summary(rows)
