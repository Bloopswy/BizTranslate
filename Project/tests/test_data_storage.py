"""Tests for data_manager: loading, saving and migrating records."""

import json
import os
import tempfile

import data_manager

from helpers import (saved)


def test_missing_and_corrupt_files_do_not_crash():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "records.json")
        assert data_manager.load_records(path) == []
        with open(path, "w") as handle:
            handle.write("{ this is not json")
        assert data_manager.load_records(path) == []
        assert os.path.exists(path + ".corrupt")


def test_save_load_roundtrip_keeps_meeting_order():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "records.json")
        rows = [saved(2, "two"), saved(1, "one"), saved(1, "other meeting", meeting="a-first")]
        assert data_manager.save_records(rows, path)
        loaded = data_manager.load_records(path)
        assert [(r["meeting"], r["seq"]) for r in loaded] == [("a-first", 1), ("m1", 1), ("m1", 2)]


def test_old_records_are_upgraded_when_loaded():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "records.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([{"id": "old", "english_translation": "Hello", "urgency": 4, "tone": "happy"}], handle)
        loaded = data_manager.load_records(path)[0]
    assert loaded["translation"] == "Hello" and loaded["intensity"] == 4
    assert loaded["meeting"] == data_manager.LEGACY_MEETING and loaded["speaker_name"] == "Earlier record"
    assert "english_translation" not in loaded and "urgency" not in loaded
