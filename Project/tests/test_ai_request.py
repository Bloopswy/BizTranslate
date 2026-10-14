"""Tests for ai_manager: build_prompt, build_request_body, call_api and analyse_record."""

import json
import os
from unittest import mock

import ai_manager
import io_manager

from helpers import (good_ai, utterance, saved)


def test_request_body_is_text_only_with_context_and_no_json_mode():
    context = [saved(1, "Hello everyone"), saved(2, "Selamat pagi", speaker="B")]
    record = utterance("What is your best price?")
    body = ai_manager.build_request_body(record, context)
    text = json.dumps(body)
    assert len(body["contents"][0]["parts"]) == 1
    assert "inline_data" not in text and "responseSchema" not in text and "responseMimeType" not in text
    user = body["contents"][0]["parts"][0]["text"]
    assert "What is your best price?" in user
    assert "Hello everyone" in user and "Selamat pagi" in user, "earlier sentences are sent as context"
    system = body["systemInstruction"]["parts"][0]["text"]
    assert "Indonesian" in system and "JSON" in system and "interpreter" in system
    assert body["generationConfig"]["temperature"] == 0


def test_first_sentence_has_no_context_and_chinese_target_is_simplified():
    user = ai_manager.build_request_body(utterance("Hi"), [])["contents"][0]["parts"][0]["text"]
    assert "first sentence" in user
    record = utterance("Hi", "B", setup=io_manager.normalise_setup(
        {"parties": {"A": {"language": "Chinese"}, "B": {"language": "English"}}}))
    assert record["target_language"] == "Chinese"
    assert "Simplified Chinese" in ai_manager.build_request_body(record)["systemInstruction"]["parts"][0]["text"]


def test_context_is_capped_and_quoted_safely():
    many = [saved(n, 'He said "no" %d' % n) for n in range(1, 11)]
    user = ai_manager.build_request_body(utterance("x"), many)["contents"][0]["parts"][0]["text"]
    assert "6. " in user and "7. " not in user, "only the last few sentences are sent"
    assert r'\"no\" 10' in user and r'\"no\" 5' in user, "the last six (5 to 10) are kept, quotes escaped"
    assert r'\"no\" 4' not in user, "older sentences are dropped"
    assert "<<<" in user and ">>>" in user


def test_default_model_is_gemma_and_env_override_works():
    assert ai_manager.get_model_name().startswith("gemma")
    with mock.patch.dict(os.environ, {"GEMMA_MODEL": "gemma-4-31b-it"}):
        assert ai_manager.get_model_name() == "gemma-4-31b-it"


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


def test_analyse_record_retries_then_succeeds_and_sends_context():
    replies = ["garbage", "Here you go: " + json.dumps(good_ai())]
    bodies = []

    def fake_call(body, key, model):
        bodies.append(body)
        return replies.pop(0)

    with mock.patch.object(ai_manager, "call_api", fake_call), mock.patch.object(ai_manager.time, "sleep"):
        result = ai_manager.analyse_record(utterance("Next"), "key", [saved(1, "Earlier sentence")])
    assert result is not None and result["translation"] == "Selamat pagi"
    assert set(result) == set(ai_manager.RESPONSE_FIELDS)
    assert len(bodies) == 2 and "Earlier sentence" in json.dumps(bodies[0])


def test_analyse_record_returns_none_when_api_down():
    with mock.patch.object(ai_manager, "call_api", return_value=None), mock.patch.object(ai_manager.time, "sleep"):
        assert ai_manager.analyse_record(utterance(), "key") is None
