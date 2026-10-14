"""Tests for ai_manager: parse_response and validate_response."""

import json

import ai_manager

from helpers import (good_ai)


def test_validate_response_accepts_good_and_rejects_bad():
    assert ai_manager.validate_response(good_ai())
    assert not ai_manager.validate_response(good_ai(tone="sarcastic"))
    assert not ai_manager.validate_response(good_ai(intensity=9))
    assert not ai_manager.validate_response(good_ai(intensity=True))
    assert not ai_manager.validate_response(good_ai(intensity=3.5))
    assert not ai_manager.validate_response(good_ai(translation_confidence=1.5))
    assert not ai_manager.validate_response(good_ai(detected_language="French"))
    assert not ai_manager.validate_response(good_ai(translation=None))
    for missing_key in ai_manager.RESPONSE_FIELDS:
        incomplete = good_ai()
        del incomplete[missing_key]
        assert not ai_manager.validate_response(incomplete), missing_key


def test_parse_response_handles_fences_chatter_and_garbage():
    assert ai_manager.parse_response('{"a": 1}') == {"a": 1}
    assert ai_manager.parse_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai_manager.parse_response('Sure! Here it is: {"a": {"b": 2}} Hope that helps.') == {"a": {"b": 2}}
    assert ai_manager.parse_response("not json") is None
    assert ai_manager.parse_response("{broken") is None
    assert ai_manager.parse_response("[1, 2]") is None
    assert ai_manager.parse_response(None) is None
