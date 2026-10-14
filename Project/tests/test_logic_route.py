"""Tests for logic_manager: route (the final outcome)."""


from helpers import (good_ai, utterance, decide)


def test_tension_needs_all_three_conditions():
    base = dict(tone="angry", intensity=5, tone_confidence=0.9)
    assert decide(utterance(), good_ai(**base))["outcome"] == "TENSION"
    assert decide(utterance(), good_ai(**{**base, "intensity": 3}))["outcome"] != "TENSION"
    assert decide(utterance(), good_ai(**{**base, "tone_confidence": 0.6}))["outcome"] != "TENSION"
    assert decide(utterance(), good_ai(**{**base, "tone": "happy"}))["outcome"] != "TENSION"
    assert decide(utterance(), good_ai(**{**base, "tone": "urgent"}))["outcome"] != "TENSION"


def test_check_on_low_confidence_or_wrong_language():
    assert decide(utterance(), good_ai(language_confidence=0.3))["outcome"] == "CHECK"
    assert decide(utterance(), good_ai(translation_confidence=0.2))["outcome"] == "CHECK"
    wrong = decide(utterance("Halo", "B"), good_ai(detected_language="Chinese"))
    assert wrong["outcome"] == "CHECK" and "Mitra is set to Indonesian" in wrong["reasons"][0]
    assert decide(utterance(), good_ai(tone_confidence=0.1))["outcome"] == "ACCEPT", \
        "an unsure tone does not make the translation unreliable"


def test_tension_also_reports_translation_doubts():
    result = decide(utterance(), good_ai(tone="frustrated", intensity=5, tone_confidence=0.9,
                                                               translation_confidence=0.3))
    assert result["outcome"] == "TENSION" and len(result["reasons"]) == 2


def test_reject_and_accept():
    assert decide(utterance(), good_ai(detected_language="Other"))["outcome"] == "REJECT"
    assert decide(utterance(), good_ai(translation="  "))["outcome"] == "REJECT"
    accepted = decide(utterance(), good_ai())
    assert accepted == {"outcome": "ACCEPT", "score": 20, "reasons": ["clear and routine"]}
    assert decide(utterance(), good_ai(translation=" "))["score"] == 0
