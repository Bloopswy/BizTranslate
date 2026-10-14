

CONTEXT_SENTENCES = 3  # how many previous sentences are shown and given to the AI as context

OUTCOME_TENSION = "TENSION"
OUTCOME_CHECK = "CHECK"
OUTCOME_ACCEPT = "ACCEPT"
OUTCOME_REJECT = "REJECT"

TENSION_TONES = ("angry", "frustrated", "anxious")
TENSION_MIN_INTENSITY = 4
TENSION_MIN_TONE_CONFIDENCE = 0.7
MIN_LANGUAGE_CONFIDENCE = 0.6
MIN_TRANSLATION_CONFIDENCE = 0.6


def decide_outcome(record, ai_fields):
    """Apply the business rules. Returns {"outcome": ..., "reasons": [...]}."""
    # Rule 1 - REJECT: unusable output.
    if not ai_fields["translation"].strip():
        return {"outcome": OUTCOME_REJECT, "reasons": ["empty translation"]}
    if ai_fields["detected_language"] == "Other":
        return {"outcome": OUTCOME_REJECT,
                "reasons": ["language is not English, Indonesian or Chinese"]}

    # Rule 2 - things that make the translation less trustworthy.
    check_reasons = []
    if ai_fields["language_confidence"] < MIN_LANGUAGE_CONFIDENCE:
        check_reasons.append("low language confidence (%.2f)" % ai_fields["language_confidence"])
    if ai_fields["translation_confidence"] < MIN_TRANSLATION_CONFIDENCE:
        check_reasons.append("low translation confidence (%.2f)" % ai_fields["translation_confidence"])
    expected = record.get("speaker_language")
    if expected and expected != ai_fields["detected_language"]:
        check_reasons.append("%s is set to %s but the AI heard %s"
                             % (record.get("speaker_name", "the speaker"), expected,
                                ai_fields["detected_language"]))

    # Rule 3 - TENSION: multi-condition rule on three AI output fields.
    if (
        ai_fields["tone"] in TENSION_TONES
        and ai_fields["intensity"] >= TENSION_MIN_INTENSITY
        and ai_fields["tone_confidence"] >= TENSION_MIN_TONE_CONFIDENCE
    ):
        reasons = ["%s tone (confidence %.2f) at intensity %d"
                   % (ai_fields["tone"], ai_fields["tone_confidence"], ai_fields["intensity"])]
        return {"outcome": OUTCOME_TENSION, "reasons": reasons + check_reasons}

    if check_reasons:
        return {"outcome": OUTCOME_CHECK, "reasons": check_reasons}

    # Rule 4 - ACCEPT.
    return {"outcome": OUTCOME_ACCEPT, "reasons": ["clear and routine"]}
