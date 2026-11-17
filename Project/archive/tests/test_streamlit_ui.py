"""Tests for Streamlit screens in io_manager.py and app.py (Streamlit replaced by a stub)."""

import json
import os
import sys
from unittest import mock

import ai_manager
import data_manager
import io_manager

from helpers import (make_setup, good_ai, saved, filter_sample, make_streamlit_stub, stub_modules, answer, clicking)


def test_escape_markdown_protects_prices_and_lists():
    escaped = io_manager.escape_markdown("We offer $4,800 per ton. 1. First *bold* [link](x)")
    assert "\\$4,800" in escaped and "1\\." in escaped and "\\*bold\\*" in escaped and "\\[link\\]" in escaped
    assert io_manager.escape_markdown("\u4F60\u597D") == "\u4F60\u597D"


def run_app_with_stub(submitted, existing, setup_meeting=None):
    """Execute app.py against the stub. Returns (saved snapshots, stub)."""
    import importlib
    snapshots = []
    stub = make_streamlit_stub()
    answer(stub, text_input={"meeting_name": setup_meeting} if setup_meeting else None)
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
            mock.patch.object(data_manager, "load_records", lambda path=None: list(existing)), \
            mock.patch.object(data_manager, "save_records", lambda recs, path=None: snapshots.append(list(recs)) or True), \
            mock.patch.object(io_manager, "ui_live_input", lambda setup: submitted(setup) if callable(submitted) else submitted), \
            mock.patch.object(ai_manager, "analyse_record",
                              lambda r, k, context=None, model=None: good_ai(tone="angry", intensity=5)), \
            mock.patch.dict(sys.modules, stub_modules(stub)):
        sys.modules.pop("app", None)
        importlib.import_module("app")
        sys.modules.pop("app", None)
    return snapshots, stub


def shown_text(stub):
    """Everything passed to st.markdown / st.caption / st.subheader, joined."""
    calls = stub.markdown.call_args_list + stub.caption.call_args_list + stub.subheader.call_args_list
    return "\n".join(str(call.args[0]) for call in calls if call.args)


def test_app_renders_empty_and_with_a_meeting_history():
    snapshots, stub = run_app_with_stub([], [], "m1")
    assert snapshots == [] and "Nothing has been said" in "".join(str(c) for c in stub.info.call_args_list)
    history = [saved(n, "sentence %d" % n) for n in range(1, 7)]
    snapshots, stub = run_app_with_stub([], history, "m1")
    text = shown_text(stub)
    assert snapshots == [] and "Previous 3 sentences" in text and "Latest translation" in text
    assert "sentence 6" in text and "sentence 5" in text and "sentence 3" in text
    assert "sentence 2" in text, "the Transcript tab lists the whole meeting"


def test_app_translates_a_submitted_sentence_and_shows_it():
    def submitted(setup):
        return [io_manager.make_utterance(setup, "B", "Harganya terlalu mahal!", "2026-10-14T09:30:00+00:00")[0]]

    snapshots, stub = run_app_with_stub(submitted, [], "m1")
    assert len(snapshots) == 1
    record = snapshots[0][0]
    assert record["outcome"] == "TENSION" and record["speaker"] == "B" and record["seq"] == 1
    assert record["target_language"] == "English" and record["listener_name"] == "Party A"
    assert stub.warning.called, "a tense moment is called out"
    assert "Harganya terlalu mahal" in shown_text(stub)


def test_app_requires_an_api_key_before_translating():
    import importlib
    stub = make_streamlit_stub()
    answer(stub)
    sentence = [io_manager.make_utterance(io_manager.default_setup(), "A", "Hello")[0]]
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}), \
            mock.patch.object(io_manager, "load_env_file", return_value=0), \
            mock.patch.object(data_manager, "load_records", lambda path=None: []), \
            mock.patch.object(io_manager, "ui_live_input", lambda setup: sentence), \
            mock.patch.object(ai_manager, "analyse_record", side_effect=AssertionError("must not call the API")), \
            mock.patch.dict(sys.modules, stub_modules(stub)):
        sys.modules.pop("app", None)
        importlib.import_module("app")
        sys.modules.pop("app", None)
    assert stub.error.called


def test_sidebar_builds_the_meeting_setup_and_time_zone():
    stub = make_streamlit_stub()
    answer(stub,
           selectbox={"language_A": "Indonesian", "language_B": "Chinese", "timezone_choice": "Asia/Singapore"},
           text_input={"meeting_name": "board", "name_A": "Budi", "name_B": "Li"})
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        key, setup, tz = io_manager.ui_sidebar("abc", "gemma-x", "base")
    assert key == "abc" and tz == "Asia/Singapore"
    assert setup == {"meeting": "board", "parties": {"A": {"name": "Budi", "language": "Indonesian"},
                                                    "B": {"name": "Li", "language": "Chinese"}}}
    assert not stub.warning.called

    stub = make_streamlit_stub()
    answer(stub, selectbox={"language_A": "Chinese", "language_B": "Chinese", "timezone_choice": io_manager.AUTO_TIMEZONE})
    stub.context.timezone = "Asia/Jakarta"
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        _key, _setup, tz = io_manager.ui_sidebar("abc", "gemma-x")
    assert stub.warning.called, "same language for both parties is called out"
    assert tz == "Asia/Jakarta", "Auto uses the browser's time zone"


def test_new_meeting_button_gives_a_fresh_name():
    stub = make_streamlit_stub()
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        io_manager._start_new_meeting()
    assert stub.session_state["meeting_name"].startswith("meeting-20")


def test_conversation_panel_shows_latest_big_then_previous_with_timestamps():
    rows = [saved(n, "sentence %d" % n, translation="Terjemahan $%d" % n) for n in range(1, 5)]
    stub = make_streamlit_stub()
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        io_manager.ui_conversation_panel(rows[-1], rows[:-1], "Asia/Singapore", 3)
    text = shown_text(stub)
    assert "### Terjemahan \\$4" in text, "latest translation is large, and $ is escaped"
    assert "Previous 3 sentences" in text
    for minute in (1, 2, 3):
        assert "`17:0%d:00`" % minute in text, "previous sentences carry their own timestamps (UTC+8 here)"
    assert "17:04:00" in text, "the latest has a timestamp too"


def test_conversation_panel_flags_tension_check_and_reject():
    for outcome, method in (("TENSION", "warning"), ("CHECK", "info"), ("REJECT", "error")):
        stub = make_streamlit_stub()
        with mock.patch.dict(sys.modules, stub_modules(stub)):
            io_manager.ui_conversation_panel(saved(1, outcome=outcome, reasons=["because"]), [], "UTC", 3)
        assert getattr(stub, method).called, outcome
    stub = make_streamlit_stub()
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        io_manager.ui_conversation_panel(saved(1), [], "UTC", 3)
    assert not (stub.warning.called or stub.error.called)


def live_input_run(state, clicked=(), speaker="B", audio=True, texts=None, files=None):
    """One run of the real ui_live_input() against the stub, sharing `state` between runs."""
    stub = make_streamlit_stub(state)
    stub.radio.return_value = speaker
    stub.audio_input.return_value = (mock.MagicMock(getvalue=lambda: b"fake-wav") if audio else None)
    stub.file_uploader.return_value = files or []
    clicking(stub, *clicked)
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        return io_manager.ui_live_input(make_setup()), stub


def test_voice_flow_transcribe_in_speakers_language_edit_then_translate():
    state = {}
    with mock.patch.object(io_manager, "transcribe_audio", return_value=("Berapa harganya", None, None)) as fake:
        submitted, _ = live_input_run(state, clicked=("voice_transcribe",))
    assert submitted == [] and state["voice_transcript"] == "Berapa harganya"
    assert fake.call_args.args[1] == "id-ID", "party B speaks Indonesian, so Whisper is told Indonesian"

    state["voice_transcript"] = "Berapa harga per ton?"  # the user fixes the text
    submitted, _ = live_input_run(state, clicked=("voice_translate",))
    assert submitted == [], "the click is handled by the next run, like Streamlit's callbacks"
    assert "voice_transcript" not in state and state["voice_counter"] == 1, "box cleared, fresh recorder"
    submitted, _ = live_input_run(state)
    assert len(submitted) == 1
    record = submitted[0]
    assert (record["speaker"], record["speaker_name"], record["target_language"]) == ("B", "Mitra", "English")
    assert record["transcript"] == "Berapa harga per ton?" and record["input_type"] == "voice"
    assert io_manager.valid_timestamp(record["timestamp"])
    submitted, _ = live_input_run(state)
    assert submitted == [], "a sentence is submitted exactly once"


def test_voice_flow_reports_problems():
    state = {}
    with mock.patch.object(io_manager, "transcribe_audio", return_value=("", None, "engine missing")):
        _, stub = live_input_run(state, clicked=("voice_transcribe",))
    assert stub.error.called and "voice_transcript" not in state
    with mock.patch.object(io_manager, "transcribe_audio", return_value=("", None, None)):
        _, stub = live_input_run(state, clicked=("voice_transcribe",))
    assert stub.warning.called
    stub = make_streamlit_stub({})
    stub.audio_input.return_value = mock.MagicMock(getvalue=lambda: b"")
    clicking(stub, "voice_transcribe")
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        io_manager.ui_live_input(make_setup())
    assert stub.error.called


def test_typed_text_flow_clears_the_box_and_targets_the_other_party():
    state = {"text_message": "Our best price is $4,800."}
    live_input_run(state, clicked=("text_translate",), speaker="A")
    assert state["text_message"] == "", "the box is emptied for the next sentence"
    submitted, _ = live_input_run(state, speaker="A")
    assert len(submitted) == 1 and submitted[0]["transcript"] == "Our best price is $4,800."
    assert (submitted[0]["speaker_name"], submitted[0]["target_language"], submitted[0]["input_type"]) == ("Acme", "Indonesian", "text")


def test_translating_an_empty_box_shows_an_error():
    state = {"text_message": "   "}
    live_input_run(state, clicked=("text_translate",))
    submitted, stub = live_input_run(state)
    assert submitted == [] and stub.error.called


def test_uploading_a_meeting_file_returns_its_sentences():
    content = json.dumps({"meeting": "deal", "utterances": [
        {"speaker": "A", "timestamp": "2026-10-14T09:00:00+08:00", "transcript": "Hello"},
        {"speaker": "B", "timestamp": "2026-10-14T09:00:05+08:00", "transcript": "Halo"}]}).encode("utf-8")
    uploaded = mock.MagicMock(getvalue=lambda: content)
    uploaded.name = "deal.json"
    submitted, _ = live_input_run({}, clicked=("translate_files",), files=[uploaded, uploaded])
    assert [r["transcript"] for r in submitted] == ["Hello", "Halo"], "the same file twice is read once"
    broken = mock.MagicMock(getvalue=lambda: b"\xff\xfe\x00bad")
    broken.name = "broken.txt"
    submitted, stub = live_input_run({}, clicked=("translate_files",), files=[broken])
    assert submitted == [] and stub.error.called


def run_filter_tab(selections, existing, match_label="All of them (AND)"):
    """Render the real app, choosing filter values. Returns the mock that received the matches."""
    import importlib
    stub = make_streamlit_stub()
    answer(stub)

    def make_column():
        column = mock.MagicMock()
        column.multiselect.side_effect = lambda label, options=None, **kw: selections.get(kw.get("key"), [])
        return column

    stub.columns.side_effect = lambda spec: [make_column() for _ in range(spec if isinstance(spec, int) else len(spec))]
    stub.radio.return_value = match_label
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
            mock.patch.object(data_manager, "load_records", lambda path=None: list(existing)), \
            mock.patch.object(io_manager, "ui_live_input", lambda setup: []), \
            mock.patch.object(io_manager, "ui_filter_results", mock.MagicMock()) as shown, \
            mock.patch.dict(sys.modules, stub_modules(stub)):
        sys.modules.pop("app", None)
        importlib.import_module("app")
        sys.modules.pop("app", None)
    return shown


def test_filter_tab_applies_the_selected_boxes_and_match_mode():
    rows = filter_sample()
    shown = run_filter_tab({"filter_tones": ["angry"], "filter_languages": ["Chinese"]}, rows)
    matched, total, tz = shown.call_args.args
    assert [r["seq"] for r in matched] == [3] and total == 4 and tz == "UTC"
    shown = run_filter_tab({"filter_tones": ["angry"], "filter_languages": ["Chinese"]}, rows, "Any of them (OR)")
    assert [r["seq"] for r in shown.call_args.args[0]] == [1, 2, 3]
    shown = run_filter_tab({"filter_speakers": ["Mitra"]}, rows)
    assert [r["seq"] for r in shown.call_args.args[0]] == [2, 3]
    assert len(run_filter_tab({}, rows).call_args.args[0]) == 4, "no selections means no filtering"


def test_filter_tab_with_no_records_shows_a_hint_instead_of_crashing():
    assert not run_filter_tab({"filter_tones": ["angry"]}, []).called


def test_download_buttons_in_two_tabs_do_not_share_keys():
    keys = []

    def make_column():
        column = mock.MagicMock()
        column.download_button.side_effect = lambda *a, **kw: keys.append(kw.get("key"))
        return column

    stub = make_streamlit_stub()
    stub.columns.side_effect = lambda spec: [make_column() for _ in range(spec if isinstance(spec, int) else len(spec))]
    rows = filter_sample()
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        io_manager.ui_downloads(rows, "UTC", key_prefix="meeting", file_stem="m1")
        io_manager.ui_filter_results(rows[:2], len(rows), "UTC")
        io_manager.ui_downloads([], "UTC")
    assert len(keys) == 6 and len(set(keys)) == 6


def test_meeting_picker_defaults_to_the_current_meeting():
    stub = make_streamlit_stub()
    stub.selectbox.side_effect = lambda label, options, **kw: options[kw["index"]]
    with mock.patch.dict(sys.modules, stub_modules(stub)):
        assert io_manager.ui_meeting_picker(["a", "m1", "z"], "m1") == "m1"
        assert io_manager.ui_meeting_picker([], "fresh") == "fresh"
        assert io_manager.ui_meeting_picker(["a"], "fresh") == "fresh", "a brand-new meeting is listed too"
