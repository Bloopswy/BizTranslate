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


def good_ai(**overrides):
    fields = {
        "detected_language": "English", "language_confidence": 0.95,
        "english_translation": "Hello, my order is late.",
        "tone": "neutral", "tone_confidence": 0.9, "urgency": 2,
        "tone_reason": "Calm statement.",
    }
    fields.update(overrides)
    return fields


def raw(text="hello", lang="en-US"):
    return {"id": io_manager.make_record_id(lang, text), "timestamp": "2026-01-01T00:00:00Z",
            "selected_lang": lang, "transcript": text}


# ---- ai_manager (Gemma, text only) ----

def test_request_body_is_text_only_and_has_no_json_mode():
    body = ai_manager.build_request_body(raw("tolong cepat"))
    text = json.dumps(body)
    assert len(body["contents"][0]["parts"]) == 1
    assert "inline_data" not in text and "responseSchema" not in text and "responseMimeType" not in text
    assert "tolong cepat" in body["contents"][0]["parts"][0]["text"]
    assert "JSON" in body["systemInstruction"]["parts"][0]["text"]
    assert body["generationConfig"]["temperature"] == 0


def test_default_model_is_gemma_and_env_override_works():
    assert ai_manager.get_model_name().startswith("gemma")
    with mock.patch.dict(os.environ, {"GEMMA_MODEL": "gemma-4-31b-it"}):
        assert ai_manager.get_model_name() == "gemma-4-31b-it"


def test_validate_schema_accepts_good_and_rejects_bad():
    assert ai_manager.validate_schema(good_ai())
    assert not ai_manager.validate_schema(good_ai(tone="sarcastic"))
    assert not ai_manager.validate_schema(good_ai(urgency=9))
    assert not ai_manager.validate_schema(good_ai(urgency=True))
    assert not ai_manager.validate_schema(good_ai(urgency=3.5))
    assert not ai_manager.validate_schema(good_ai(tone_confidence=1.5))
    assert not ai_manager.validate_schema(good_ai(detected_language="French"))
    missing = good_ai()
    del missing["tone_reason"]
    assert not ai_manager.validate_schema(missing)


def test_parse_response_handles_fences_chatter_and_garbage():
    assert ai_manager.parse_response('{"a": 1}') == {"a": 1}
    assert ai_manager.parse_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai_manager.parse_response('Sure! Here it is: {"a": {"b": 2}} Hope that helps.') == {"a": {"b": 2}}
    assert ai_manager.parse_response("not json") is None
    assert ai_manager.parse_response("{broken") is None
    assert ai_manager.parse_response("[1, 2]") is None
    assert ai_manager.parse_response(None) is None


def test_call_api_skips_thought_parts_and_handles_http_errors():
    good = mock.MagicMock(status_code=200)
    good.json.return_value = {"candidates": [{"content": {"parts": [
        {"text": "thinking...", "thought": True}, {"text": '{"ok": true}'}]}}]}
    with mock.patch.object(ai_manager.requests, "post", return_value=good):
        assert ai_manager.call_api({}, "k", "m") == '{"ok": true}'
    bad = mock.MagicMock(status_code=429, text="rate limited")
    with mock.patch.object(ai_manager.requests, "post", return_value=bad):
        assert ai_manager.call_api({}, "k", "m") is None
    with mock.patch.object(ai_manager.requests, "post", side_effect=ai_manager.requests.ConnectionError("down")):
        assert ai_manager.call_api({}, "k", "m") is None
    empty = mock.MagicMock(status_code=200)
    empty.json.return_value = {"candidates": []}
    with mock.patch.object(ai_manager.requests, "post", return_value=empty):
        assert ai_manager.call_api({}, "k", "m") is None


def test_analyse_record_retries_then_succeeds():
    replies = ["garbage", "Here you go: " + json.dumps(good_ai())]
    with mock.patch.object(ai_manager, "call_api", side_effect=lambda b, k, m: replies.pop(0)), \
            mock.patch.object(ai_manager.time, "sleep"):
        result = ai_manager.analyse_record(raw(), "key")
    assert result is not None and result["tone"] == "neutral"
    assert set(result) == set(ai_manager.RESPONSE_FIELDS)


def test_analyse_record_returns_none_when_api_down():
    with mock.patch.object(ai_manager, "call_api", return_value=None), mock.patch.object(ai_manager.time, "sleep"):
        assert ai_manager.analyse_record(raw(), "key") is None


# ---- speech to text (Whisper replaced by a fake) ----

def fake_whisper_module(language="en", probs=None, text=" hello there "):
    """A fake faster_whisper module whose model records how it was called."""
    model = mock.MagicMock()
    info = SimpleNamespace(language=language, all_language_probs=probs)
    model.transcribe.side_effect = lambda *a, **k: (iter([SimpleNamespace(text=text)]), info)
    module = mock.MagicMock()
    module.WhisperModel.return_value = model
    return module, model


def test_transcribe_audio_with_chosen_language():
    module, model = fake_whisper_module()
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": module}):
        text, code, error = io_manager.transcribe_audio(b"wav", "id-ID")
    io_manager._speech_models.clear()
    assert (text, code, error) == ("hello there", "id-ID", None)
    assert model.transcribe.call_count == 1
    assert model.transcribe.call_args.kwargs["language"] == "id"


def test_transcribe_audio_auto_detect_is_restricted_to_supported_languages():
    # Whisper's top guess is Malay; Indonesian is the best of our three languages.
    module, model = fake_whisper_module(language="ms", probs=[("ms", 0.5), ("id", 0.4), ("en", 0.1)])
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": module}):
        text, code, error = io_manager.transcribe_audio(b"wav", None)
    io_manager._speech_models.clear()
    assert error is None and code == "id-ID"
    assert model.transcribe.call_count == 2
    assert model.transcribe.call_args.kwargs["language"] == "id"


def test_transcribe_audio_reports_errors_instead_of_crashing():
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": None}):  # simulates "not installed"
        text, code, error = io_manager.transcribe_audio(b"wav", None)
    assert text == "" and code is None and "faster-whisper" in error
    module, model = fake_whisper_module()
    model.transcribe.side_effect = RuntimeError("bad audio")
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": module}):
        text, code, error = io_manager.transcribe_audio(b"wav", "en-US")
    io_manager._speech_models.clear()
    assert text == "" and "bad audio" in error


def test_pick_supported_language():
    assert io_manager.pick_supported_language([("fr", 0.9), ("zh", 0.05), ("en", 0.02)]) == "zh"
    assert io_manager.pick_supported_language([("fr", 0.9)]) is None
    assert io_manager.pick_supported_language(None) is None


def test_make_voice_record():
    record, problem = io_manager.make_voice_record("  halo  ", "id-ID")
    assert problem is None and record["input_type"] == "voice" and record["transcript"] == "halo"
    assert record["selected_lang"] == "id-ID"
    assert io_manager.make_voice_record("   ", "id-ID")[0] is None


# ---- logic_manager ----

def test_escalate_needs_all_three_conditions():
    base = dict(tone="angry", urgency=5, tone_confidence=0.9)
    assert logic_manager.decide_outcome(raw(), good_ai(**base))["outcome"] == "ESCALATE"
    assert logic_manager.decide_outcome(raw(), good_ai(**{**base, "urgency": 3}))["outcome"] != "ESCALATE"
    assert logic_manager.decide_outcome(raw(), good_ai(**{**base, "tone_confidence": 0.6}))["outcome"] != "ESCALATE"
    assert logic_manager.decide_outcome(raw(), good_ai(**{**base, "tone": "happy"}))["outcome"] != "ESCALATE"


def test_review_on_low_confidence_or_language_mismatch():
    assert logic_manager.decide_outcome(raw(), good_ai(language_confidence=0.3))["outcome"] == "REVIEW"
    assert logic_manager.decide_outcome(raw(), good_ai(tone_confidence=0.2))["outcome"] == "REVIEW"
    mismatch = logic_manager.decide_outcome(raw(lang="zh-CN"), good_ai(detected_language="English"))
    assert mismatch["outcome"] == "REVIEW"


def test_reject_and_accept():
    assert logic_manager.decide_outcome(raw(), good_ai(detected_language="Other"))["outcome"] == "REJECT"
    assert logic_manager.decide_outcome(raw(), good_ai(english_translation="  "))["outcome"] == "REJECT"
    assert logic_manager.decide_outcome(raw(), good_ai())["outcome"] == "ACCEPT"


# ---- data_manager ----

def test_missing_and_corrupt_files_do_not_crash():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "records.json")
        assert data_manager.load_records(path) == []
        with open(path, "w") as handle:
            handle.write("{ this is not json")
        assert data_manager.load_records(path) == []
        assert os.path.exists(path + ".corrupt")


def test_save_load_roundtrip_and_filter():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "records.json")
        records = [
            {"id": "b", "timestamp": "2", "outcome": "ACCEPT", "tone": "happy", "detected_language": "English", "priority_score": 10},
            {"id": "a", "timestamp": "1", "outcome": "ESCALATE", "tone": "angry", "detected_language": "Chinese", "priority_score": 80},
        ]
        assert data_manager.save_records(records, path)
        loaded = data_manager.load_records(path)
        assert [r["id"] for r in loaded] == ["a", "b"]
        assert [r["id"] for r in data_manager.filter_records(loaded, outcome="ESCALATE")] == ["a"]
        assert [r["id"] for r in data_manager.filter_records(loaded, language="English", min_priority=5)] == ["b"]


# ---- io_manager ----

def test_input_validation_and_stable_ids():
    ok, problem = io_manager.normalise_input_record({"transcript": " hi ", "selected_lang": "en-US"})
    assert problem is None and ok["transcript"] == "hi"
    again, _ = io_manager.normalise_input_record({"transcript": "hi", "selected_lang": "en-US"})
    assert ok["id"] == again["id"]
    assert io_manager.normalise_input_record({"transcript": ""})[0] is None
    assert io_manager.normalise_input_record("nope")[0] is None


def test_read_input_file_skips_bad_items():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "t.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([{"transcript": "halo", "selected_lang": "id-ID"}, {"transcript": ""}, 5], handle)
        records, errors = io_manager.read_input_file(path)
        assert len(records) == 1 and len(errors) == 2
        assert io_manager.read_input_file(os.path.join(folder, "missing.json"))[0] == []


def test_parse_input_content_handles_json_txt_and_bad_input():
    records, errors = io_manager.parse_input_content("a.txt", "one\n\ntwo\n")
    assert len(records) == 2 and not errors
    records, errors = io_manager.parse_input_content("a.json", "{not json")
    assert records == [] and len(errors) == 1
    records, errors = io_manager.parse_input_content("a.json", '{"transcript": "x"}')
    assert records == [] and len(errors) == 1


def test_records_to_csv_has_header_and_rows():
    text = io_manager.records_to_csv([{"id": "a", "outcome": "ACCEPT", "reasons": ["x", "y"], "extra": 1}])
    lines = text.strip().splitlines()
    assert lines[0].startswith("id,") and "x; y" in lines[1]


def test_load_env_file_parses_and_respects_existing_values():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, ".env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# comment\nTEST_KEY_A=abc\nexport TEST_KEY_B=\"quoted value\"\nTEST_KEY_C=keep\n\nbadline\n")
        os.environ["TEST_KEY_C"] = "already-set"
        try:
            assert io_manager.load_env_file(path) == 2
            assert os.environ["TEST_KEY_A"] == "abc"
            assert os.environ["TEST_KEY_B"] == "quoted value"
            assert os.environ["TEST_KEY_C"] == "already-set"
            assert io_manager.load_env_file(os.path.join(folder, "missing.env")) == 0
        finally:
            for name in ("TEST_KEY_A", "TEST_KEY_B", "TEST_KEY_C"):
                os.environ.pop(name, None)


# ---- full pipeline ----

def test_pipeline_is_idempotent_and_deterministic():
    calls = []

    def fake_analyse(record, api_key, model=None):
        calls.append(record["id"])
        return good_ai(english_translation="Translated: " + record["transcript"])

    with mock.patch.object(ai_manager, "analyse_record", fake_analyse), \
            mock.patch.object(data_manager, "save_records", return_value=True):
        batch = [raw("one"), raw("two")]
        first = main.process_records(batch, [], "key")
        snapshot = json.dumps(data_manager.sort_records(first), sort_keys=True)
        second = main.process_records(batch, first, "key")
    assert len(calls) == 2, "second run must not call the API again"
    assert json.dumps(data_manager.sort_records(second), sort_keys=True) == snapshot
    assert all(r["english_translation"].startswith("Translated:") for r in second)


def test_failed_ai_is_not_saved_and_does_not_crash():
    with mock.patch.object(ai_manager, "analyse_record", return_value=None):
        records, status = main.process_record(raw("x"), [], "key")
    assert records == [] and status == "failed"


def test_voice_record_is_saved_as_voice_with_no_audio():
    record, _ = io_manager.make_voice_record("Selamat pagi", "id-ID")
    with mock.patch.object(ai_manager, "analyse_record",
                           return_value=good_ai(detected_language="Indonesian", english_translation="Good morning")):
        records, status = main.process_record(record, [], "key")
    assert status == "processed" and records[0]["input_type"] == "voice"
    assert "audio" not in json.dumps(records[0]).lower()


# ---- Streamlit app smoke tests (Streamlit replaced by a stub) ----

def make_streamlit_stub(session_state=None):
    def make_column():
        column = mock.MagicMock()
        column.selectbox.return_value = "All"
        column.slider.return_value = 0
        return column

    stub = mock.MagicMock()
    stub.columns.side_effect = lambda spec: [make_column() for _ in range(spec if isinstance(spec, int) else len(spec))]
    stub.tabs.side_effect = lambda names: [mock.MagicMock() for _ in names]
    stub.selectbox.return_value = "All"
    stub.slider.return_value = 0
    stub.text_input.return_value = ""
    stub.session_state = {} if session_state is None else session_state
    return stub


def stub_modules(stub):
    return {"streamlit": stub, "streamlit.components": stub.components,
            "streamlit.components.v1": stub.components.v1, "pandas": mock.MagicMock()}


def run_app_with_stub(submitted, existing):
    """Execute app.py's run_app() against the stub. Returns the list of saved snapshots."""
    import importlib
    saved = []
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
            mock.patch.object(data_manager, "load_records", lambda path=None: list(existing)), \
            mock.patch.object(data_manager, "save_records", lambda recs, path=None: saved.append(list(recs)) or True), \
            mock.patch.object(io_manager, "ui_input_tabs", lambda: submitted), \
            mock.patch.object(ai_manager, "analyse_record", lambda r, k, model=None: good_ai(tone="angry", urgency=5)), \
            mock.patch.dict(sys.modules, stub_modules(make_streamlit_stub())):
        sys.modules.pop("app", None)
        importlib.import_module("app")
        sys.modules.pop("app", None)
    return saved


def test_streamlit_app_renders_empty_and_with_records():
    assert run_app_with_stub([], []) == []
    existing = [{"id": "z", "timestamp": "1", "outcome": "ACCEPT", "tone": "neutral", "detected_language": "English",
                 "priority_score": 20, "english_translation": "hi", "transcript": "hi", "reasons": ["clear and routine"],
                 "language_confidence": 0.9, "tone_confidence": 0.9, "urgency": 2, "tone_reason": "calm"}]
    assert run_app_with_stub([], existing) == []


def test_streamlit_app_processes_a_submitted_voice_transcript():
    record, _ = io_manager.make_voice_record("Tolong cepat", "id-ID")
    saved = run_app_with_stub([record], [])
    assert len(saved) == 1
    assert saved[0][0]["outcome"] == "ESCALATE" and saved[0][0]["input_type"] == "voice"


def test_voice_tab_flow_transcribe_then_analyse():
    """Drive the real ui_input_tabs(): click Transcribe, then Analyse transcript."""
    state = {}
    audio = mock.MagicMock()
    audio.getvalue.return_value = b"fake-wav"

    def run(clicked):
        stub = make_streamlit_stub(state)
        stub.audio_input.return_value = audio
        stub.selectbox.return_value = "Indonesian"
        stub.button.side_effect = lambda label, **kw: kw.get("key") == clicked
        with mock.patch.dict(sys.modules, stub_modules(stub)), \
                mock.patch.object(io_manager, "transcribe_audio", return_value=("Tolong cepat", "id-ID", None)) as fake:
            return io_manager.ui_input_tabs(), fake

    submitted, fake = run("voice_transcribe")
    assert submitted == [] and state["voice_transcript"] == "Tolong cepat"
    assert fake.call_args.args[1] == "id-ID", "chosen language must reach the transcriber"

    state["voice_transcript"] = "Tolong cepat sekali"  # the user edits the text box
    submitted, _ = run("voice_analyse")
    assert len(submitted) == 1
    assert submitted[0]["transcript"] == "Tolong cepat sekali" and submitted[0]["input_type"] == "voice"
    assert submitted[0]["selected_lang"] == "id-ID"


def test_voice_tab_reports_transcription_error_and_empty_audio():
    state = {}
    audio = mock.MagicMock()
    audio.getvalue.return_value = b"fake-wav"
    stub = make_streamlit_stub(state)
    stub.audio_input.return_value = audio
    stub.selectbox.return_value = "Auto-detect"
    stub.button.side_effect = lambda label, **kw: kw.get("key") == "voice_transcribe"
    with mock.patch.dict(sys.modules, stub_modules(stub)), \
            mock.patch.object(io_manager, "transcribe_audio", return_value=("", None, "engine missing")):
        assert io_manager.ui_input_tabs() == []
    assert "voice_transcript" not in state
    assert stub.error.called

    stub = make_streamlit_stub({})
    stub.audio_input.return_value = audio
    stub.selectbox.return_value = "Auto-detect"
    stub.button.side_effect = lambda label, **kw: kw.get("key") == "voice_transcribe"
    with mock.patch.dict(sys.modules, stub_modules(stub)), \
            mock.patch.object(io_manager, "transcribe_audio", return_value=("", None, None)):
        assert io_manager.ui_input_tabs() == []
    assert stub.warning.called


def run_all():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
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
