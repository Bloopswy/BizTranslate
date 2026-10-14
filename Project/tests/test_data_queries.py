"""Tests for data_manager: meeting history, last sentences and filtering."""


import data_manager

from helpers import (saved, filter_sample)


def seqs_and_meetings(records):
    return [(r["meeting"], r["seq"]) for r in records]


def test_sequence_and_last_sentences():
    rows = [saved(n, "s%d" % n) for n in range(1, 6)] + [saved(1, "elsewhere", meeting="m2")]
    assert data_manager.next_sequence(rows, "m1") == 6 and data_manager.next_sequence(rows, "new") == 1
    assert [r["seq"] for r in data_manager.last_sentences(rows, "m1", 3)] == [3, 4, 5]
    assert data_manager.last_sentences(rows, "m1", 0) == [] and len(data_manager.last_sentences(rows, "m1", 99)) == 5
    assert data_manager.list_meetings(rows) == ["m1", "m2"]
    assert [r["seq"] for r in data_manager.meeting_records(rows, "m1")] == [1, 2, 3, 4, 5]


def test_latest_with_context_gives_the_three_sentences_before_the_latest():
    rows = [saved(n, "s%d" % n) for n in range(1, 7)]
    latest, previous = data_manager.latest_with_context(rows, "m1", 3)
    assert latest["seq"] == 6 and [r["seq"] for r in previous] == [3, 4, 5]
    latest, previous = data_manager.latest_with_context(rows[:2], "m1", 3)
    assert latest["seq"] == 2 and [r["seq"] for r in previous] == [1]
    assert data_manager.latest_with_context(rows[:1], "m1", 3)[1] == []
    assert data_manager.latest_with_context([], "m1", 3) == (None, [])
    assert data_manager.latest_with_context(rows, "m1", 0)[1] == []


def test_filter_by_tone_or_language_alone():
    rows = filter_sample()
    assert len(data_manager.filter_records_multi(rows)) == 4
    assert [r["seq"] for r in data_manager.filter_records_multi(rows, tones=["angry"])] == [1, 3]
    assert [r["seq"] for r in data_manager.filter_records_multi(rows, tones=["angry", "happy"])] == [1, 2, 3]
    assert [r["seq"] for r in data_manager.filter_records_multi(rows, languages=["Chinese"])] == [2, 3]
    assert [r["seq"] for r in data_manager.filter_records_multi(rows, target_languages=["English"])] == [2, 3]
    assert [r["seq"] for r in data_manager.filter_records_multi(rows, speakers=["Acme"])] == [1, 4]


def test_filter_and_vs_or():
    rows = filter_sample()
    both = data_manager.filter_records_multi(rows, tones=["angry"], languages=["Chinese"], match="all")
    either = data_manager.filter_records_multi(rows, tones=["angry"], languages=["Chinese"], match="any")
    assert [r["seq"] for r in both] == [3] and [r["seq"] for r in either] == [1, 2, 3]
    three = data_manager.filter_records_multi(rows, tones=["angry"], languages=["Chinese"], speakers=["Mitra"], match="all")
    assert [r["seq"] for r in three] == [3]


def test_filter_extra_narrowing_always_applies():
    rows = filter_sample()
    assert [r["seq"] for r in data_manager.filter_records_multi(
        rows, tones=["angry"], languages=["Chinese"], match="any", outcome="ACCEPT")] == [2]
    assert seqs_and_meetings(data_manager.filter_records_multi(rows, meeting="m2")) == [("m2", 4)]
    assert data_manager.filter_records_multi(rows, tones=["sad"]) == []
    assert data_manager.filter_records_multi([], tones=["angry"]) == []
