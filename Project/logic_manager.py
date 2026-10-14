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

CONTEXT_SENTENCES = 3  # how many previous sentences are shown and given to the AI as context

OUTCOME_TENSION = "TENSION"
OUTCOME_CHECK = "CHECK"
OUTCOME_ACCEPT = "ACCEPT"
OUTCOME_REJECT = "REJECT"

def route(record):
    """Decide the outcome. Returns {"outcome": ..., "score": ..., "reasons": [...]}."""
    findings = evaluate(record)

    if findings["reject"]:
        return {"outcome": OUTCOME_REJECT, "score": 0, "reasons": findings["reject"]}
    points = score(record)
    if findings["tension"]:  # tension wins, but still reports any translation doubts
        return {"outcome": OUTCOME_TENSION, "score": points, "reasons": findings["tension"] + findings["check"]}
    if findings["check"]:
        return {"outcome": OUTCOME_CHECK, "score": points, "reasons": findings["check"]}
    return {"outcome": OUTCOME_ACCEPT, "score": points, "reasons": ["clear and routine"]}
