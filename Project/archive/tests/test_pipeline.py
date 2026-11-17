"""Tests for main.py: the AI -> logic -> data pipeline and batch loading."""

import json
import os
import tempfile
from unittest import mock

import ai_manager
import data_manager
import io_manager
import main

from helpers import (make_setup, good_ai, utterance, saved)


def test_the_previous_three_sentences_reach_the_ai_as_context():
    existing = [saved(n, "earlier %d" % n) for n in range(1, 6)] + [saved(1, "other meeting", meeting="m2")]
    seen = {}

    def fake_analyse(record, api_key, context=None, model=None):
        seen["context"] = context
        return good_ai()

    with mock.patch.object(ai_manager, "analyse_record", fake_analyse):
        records, status = main.process_record(utterance("Now", position=99), existing, "key")
    assert status == "processed"
    assert [c["transcript"] for c in seen["context"]] == ["earlier 3", "earlier 4", "earlier 5"]
    new = data_manager.find_by_id(records, utterance("Now", position=99)["id"])
    assert new["seq"] == 6 and new["outcome"] == "ACCEPT" and new["translation"] == "Selamat pagi"


def test_pipeline_is_idempotent_and_keeps_repeated_sentences():
    calls = []

    def fake_analyse(record, api_key, context=None, model=None):
        calls.append(record["id"])
        return good_ai(translation="T: " + record["transcript"])

    batch = [utterance("Yes.", position=1), utterance("Yes.", position=2), utterance("No.", "B", position=3)]
    with mock.patch.object(ai_manager, "analyse_record", fake_analyse), \
            mock.patch.object(data_manager, "save_records", return_value=True):
        first = main.process_records(batch, [], "key", "UTC")
        snapshot = json.dumps(data_manager.sort_records(first), sort_keys=True)
        second = main.process_records(batch, first, "key", "UTC")
    assert len(first) == 3, "the same words said twice are two sentences"
    assert [r["seq"] for r in data_manager.meeting_records(first, "m1")] == [1, 2, 3]
    assert len(calls) == 3, "second run must not call the API again"
    assert json.dumps(data_manager.sort_records(second), sort_keys=True) == snapshot


def test_failed_ai_is_not_saved_and_does_not_crash():
    with mock.patch.object(ai_manager, "analyse_record", return_value=None):
        records, status = main.process_record(utterance("x"), [], "key")
    assert records == [] and status == "failed"


def test_batch_files_become_meetings_named_after_the_file():
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, "weekly sync.txt"), "w", encoding="utf-8") as handle:
            handle.write("A: Hello\nB: Halo\n")
        with open(os.path.join(folder, "named.json"), "w", encoding="utf-8") as handle:
            json.dump({"meeting": "kickoff", "utterances": [{"speaker": "A", "transcript": "Start"}]}, handle)
        with mock.patch.object(io_manager, "INPUT_DIR", folder):
            raw = main.load_raw_records_from_files(["weekly sync.txt", "named.json"], make_setup(), name_meeting_after_file=True)
            fixed = main.load_raw_records_from_files(["weekly sync.txt"], make_setup(), name_meeting_after_file=False)
    assert sorted({r["meeting"] for r in raw}) == ["kickoff", "weekly sync"]
    assert {r["meeting"] for r in fixed} == {"m1"}


def test_shipped_sample_meetings_parse_cleanly():
    root = os.path.join(os.path.dirname(__file__), "..", "input")
    for name in sorted(os.listdir(root)):
        records, errors = io_manager.read_meeting_file(os.path.join(root, name), make_setup())
        assert records and not errors, name
        assert all(r["timestamp"] for r in records)
