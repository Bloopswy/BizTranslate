"""Plain-function test runner (no classes, per the 100% procedural constraint).

Run from the project root:  python tests/run_tests.py
No network, API key, Streamlit or Whisper install needed: those are replaced with fakes.
"""

import json
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_manager
import data_manager
import io_manager
import logic_manager
import main


def test_setup():
    return io_manager.normalise_setup({
        "meeting": "m1",
        "parties": {"A": {"name": "Acme", "language": "English"}, "B": {"name": "Mitra", "language": "Indonesian"}},
    })

def test_timestamps_and_ids():
    live = io_manager.make_utterance(test_setup(), "A", "Hi")[0]
    assert live["timestamp"] and io_manager.format_clock(live["timestamp"], "UTC") != "--:--:--"
    assert io_manager.make_utterance(test_setup(), "A", "Hi", "not a time")[0]["timestamp"] == ""
    same = [utterance("Hi", position=1)["id"], utterance("Hi", position=1)["id"]]
    assert same[0] == same[1], "same sentence, same id"
    assert utterance("Hi", position=1)["id"] != utterance("Hi", position=2)["id"], "repeated lines stay distinct"
    assert utterance("Hi", timestamp="2026-10-14T09:00:01+00:00")["id"] != utterance("Hi")["id"]
    other = io_manager.normalise_setup({"meeting": "m2"}, test_setup())
    assert utterance("Hi", setup=other)["id"] != utterance("Hi")["id"], "meeting is part of the id"

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

    def test_load_env_file_parses_and_respects_existing_values():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, ".env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# comment\nTEST_KEY_A=abc\nexport TEST_KEY_B=\"quoted value\"\nTEST_KEY_C=keep\n\nbadline\n")
        os.environ["TEST_KEY_C"] = "already-set"
        try:
            assert io_manager.load_env_file(path) == 2
            assert os.environ["TEST_KEY_A"] == "abc" and os.environ["TEST_KEY_B"] == "quoted value"
            assert os.environ["TEST_KEY_C"] == "already-set"
            assert io_manager.load_env_file(os.path.join(folder, "missing.env")) == 0
        finally:
            for name in ("TEST_KEY_A", "TEST_KEY_B", "TEST_KEY_C"):
                os.environ.pop(name, None)