"""Logic layer - the domain brain.

Domain: live interpreting for a business meeting between two parties, each speaking
English, Indonesian or Chinese. The AI translates every sentence into the other party's
language and reads its tone; this layer decides how the sentence should be treated.

Three steps, each a function that takes the AI-enriched record (the sentence plus the
AI's fields):

  evaluate(record) -> which rules fired (reject / check / tension findings)
  score(record)    -> 0-100 "attention score": stronger, more negative tone scores higher
  route(record)    -> the final outcome, using evaluate() and score()

Outcomes:
  TENSION - a heated moment (negative tone, strong, and the AI is confident): both sides
            should slow down and confirm understanding
  CHECK   - the translation may be unreliable (low confidence, or the speaker used a
            different language than expected): confirm with the speaker
  ACCEPT  - clear and routine
  REJECT  - unusable (empty translation or unsupported language)
"""

CONTEXT_SENTENCES = 3 

OUTCOME_TENSION = "TENSION"
OUTCOME_CHECK = "CHECK"
OUTCOME_ACCEPT = "ACCEPT"
OUTCOME_REJECT = "REJECT"

TENSION_TONES = ("angry", "frustrated", "anxious")
TENSION_MIN_INTENSITY = 4
TENSION_MIN_TONE_CONFIDENCE = 0.7
MIN_LANGUAGE_CONFIDENCE = 0.6
MIN_TRANSLATION_CONFIDENCE = 0.6

TONE_WEIGHT = {
    "angry": 30, "frustrated": 25, "anxious": 20, "urgent": 15,
    "sad": 10, "neutral": 0, "happy": 0, "grateful": 0,
}

def evaluate(record):
    """Apply the business rules. Returns {"reject": [...], "check": [...], "tension": [...]},
    each a list of human-readable reasons (an empty list means that rule did not fire)."""
    findings = {"reject": [], "check": [], "tension": []}
    if not record["translation"].strip():
        findings["reject"].append("empty translation")
    if record["detected_language"] == "Other":
        findings["reject"].append("language is not English, Indonesian or Chinese")
    if record["language_confidence"] < MIN_LANGUAGE_CONFIDENCE:
        findings["check"].append("low language confidence (%.2f)" % record["language_confidence"])
    if record["translation_confidence"] < MIN_TRANSLATION_CONFIDENCE:
        findings["check"].append("low translation confidence (%.2f)" % record["translation_confidence"])
    expected = record.get("speaker_language")
    if expected and expected != record["detected_language"]:
        findings["check"].append("%s is set to %s but the AI heard %s"
                                 % (record.get("speaker_name", "the speaker"), expected,
                                    record["detected_language"]))
    if (
        record["tone"] in TENSION_TONES
        and record["intensity"] >= TENSION_MIN_INTENSITY
        and record["tone_confidence"] >= TENSION_MIN_TONE_CONFIDENCE
    ):
        findings["tension"].append("%s tone (confidence %.2f) at intensity %d"
                                   % (record["tone"], record["tone_confidence"], record["intensity"]))
    return findings

def route(record):
    """Decide the outcome. Returns {"outcome": ..., "score": ..., "reasons": [...]}."""
    findings = evaluate(record)

    if findings["reject"]:
        return {"outcome": OUTCOME_REJECT, "score": 0, "reasons": findings["reject"]}
    points = score(record)
    if findings["tension"]:
        return {"outcome": OUTCOME_TENSION, "score": points, "reasons": findings["tension"] + findings["check"]}
    if findings["check"]:
        return {"outcome": OUTCOME_CHECK, "score": points, "reasons": findings["check"]}
    return {"outcome": OUTCOME_ACCEPT, "score": points, "reasons": ["clear and routine"]}

def score(record):
    """Attention score from 0 to 100: intensity (10-50) plus a weight for the tone, capped at 100."""
    points = record["intensity"] * 10 + TONE_WEIGHT.get(record["tone"], 0)
    return max(0, min(100, points))
