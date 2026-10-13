"""Logic layer - the domain brain.

Domain: multilingual voice-message triage. A staff member receives voice messages
in English, Chinese or Indonesian. The AI transcribes-understands them (translation
+ tone); this layer decides what a human should do with each one.

Outcomes:
  ESCALATE - upset, high-urgency message: a person should respond first
  REVIEW   - the AI is unsure (language/tone) or the audio settings look wrong
  ACCEPT   - clear and routine: safe to handle from the English translation
  REJECT   - unusable (empty translation or unsupported language)
"""

OUTCOME_ESCALATE = "ESCALATE"
OUTCOME_REVIEW = "REVIEW"
OUTCOME_ACCEPT = "ACCEPT"
OUTCOME_REJECT = "REJECT"

SPEECH_LANG_TO_NAME = {
    "en-US": "English",
    "zh-CN": "Chinese",
    "id-ID": "Indonesian",
}

NEGATIVE_TONES = ("angry", "frustrated", "anxious", "urgent", "sad")

TONE_WEIGHT = {
    "angry": 30, "urgent": 25, "frustrated": 25, "anxious": 20,
    "sad": 15, "neutral": 0, "happy": 0, "grateful": 0,
}

ESCALATE_MIN_URGENCY = 4
ESCALATE_MIN_TONE_CONFIDENCE = 0.7
MIN_LANGUAGE_CONFIDENCE = 0.6
MIN_TONE_CONFIDENCE = 0.5


def expected_language(record):
    """Language the speaker chose in the recorder, or None if unknown."""
    return SPEECH_LANG_TO_NAME.get(record.get("selected_lang"))


def compute_priority_score(ai_fields):
    """0-100 score: urgency dominates, tone adds weight."""
    score = ai_fields["urgency"] * 10 + TONE_WEIGHT.get(ai_fields["tone"], 0)
    return max(0, min(100, score))


def decide_outcome(record, ai_fields):
    """Apply the business rules and return {outcome, priority_score, reasons}."""
    reasons = []
    score = compute_priority_score(ai_fields)

    # Rule 1 - REJECT: unusable output.
    if not ai_fields["english_translation"].strip():
        return {"outcome": OUTCOME_REJECT, "priority_score": 0, "reasons": ["empty translation"]}
    if ai_fields["detected_language"] == "Other":
        return {"outcome": OUTCOME_REJECT, "priority_score": 0,
                "reasons": ["language is not English, Chinese or Indonesian"]}

    # Rule 2 - ESCALATE: multi-condition rule on three AI output fields.
    if (
        ai_fields["tone"] in NEGATIVE_TONES
        and ai_fields["urgency"] >= ESCALATE_MIN_URGENCY
        and ai_fields["tone_confidence"] >= ESCALATE_MIN_TONE_CONFIDENCE
    ):
        reasons.append(
            "%s tone (confidence %.2f) with urgency %d"
            % (ai_fields["tone"], ai_fields["tone_confidence"], ai_fields["urgency"])
        )
        return {"outcome": OUTCOME_ESCALATE, "priority_score": score, "reasons": reasons}

    # Rule 3 - REVIEW: the AI is unsure, or the recorder language looks wrong.
    if ai_fields["language_confidence"] < MIN_LANGUAGE_CONFIDENCE:
        reasons.append("low language confidence (%.2f)" % ai_fields["language_confidence"])
    if ai_fields["tone_confidence"] < MIN_TONE_CONFIDENCE:
        reasons.append("low tone confidence (%.2f)" % ai_fields["tone_confidence"])
    chosen = expected_language(record)
    if chosen is not None and chosen != ai_fields["detected_language"]:
        reasons.append(
            "recorder set to %s but AI detected %s" % (chosen, ai_fields["detected_language"])
        )
    if reasons:
        return {"outcome": OUTCOME_REVIEW, "priority_score": score, "reasons": reasons}

    # Rule 4 - ACCEPT.
    return {"outcome": OUTCOME_ACCEPT, "priority_score": score, "reasons": ["clear and routine"]}
