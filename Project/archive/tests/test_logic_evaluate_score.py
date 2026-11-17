"""Tests for logic_manager: evaluate and score."""


import logic_manager

from helpers import (utterance, merged)


def test_evaluate_reports_each_rule_separately():
    clean = logic_manager.evaluate(merged())
    assert clean == {"reject": [], "check": [], "tension": []}
    assert len(logic_manager.evaluate(merged(translation="  "))["reject"]) == 1
    assert len(logic_manager.evaluate(merged(detected_language="Other"))["reject"]) >= 1
    doubts = logic_manager.evaluate(merged(utterance("Halo", "B"), language_confidence=0.2,
                                           translation_confidence=0.2, detected_language="Chinese"))
    assert len(doubts["check"]) == 3 and doubts["reject"] == [] and doubts["tension"] == []
    heated = logic_manager.evaluate(merged(tone="angry", intensity=5, tone_confidence=0.9))
    assert len(heated["tension"]) == 1 and heated["check"] == []


def test_evaluate_tension_rule_needs_tone_intensity_and_confidence_together():
    base = dict(tone="frustrated", intensity=4, tone_confidence=0.7)
    assert logic_manager.evaluate(merged(**base))["tension"]
    assert not logic_manager.evaluate(merged(**{**base, "intensity": 3}))["tension"]
    assert not logic_manager.evaluate(merged(**{**base, "tone_confidence": 0.69}))["tension"]
    assert not logic_manager.evaluate(merged(**{**base, "tone": "sad"}))["tension"]


def test_score_is_intensity_plus_tone_weight():
    assert logic_manager.score(merged(tone="neutral", intensity=1)) == 10
    assert logic_manager.score(merged(tone="neutral", intensity=2)) == 20
    assert logic_manager.score(merged(tone="angry", intensity=5)) == 80
    assert logic_manager.score(merged(tone="happy", intensity=5)) == 50
    assert logic_manager.score(merged(tone="angry", intensity=5)) > logic_manager.score(merged(tone="sad", intensity=5))
    assert 0 <= logic_manager.score(merged(tone="made-up", intensity=1)) <= 100, "unknown tones weigh nothing"
