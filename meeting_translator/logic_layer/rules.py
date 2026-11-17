"""Business rules.

    Rule (abstract base class)
      |- RejectRule              -> REJECT   unusable output
      |- ConfidenceCheckRule     -> CHECK    low language / translation confidence
      |- LanguageMismatchRule    -> CHECK    speaker used another language than expected
      '- TensionRule             -> TENSION  multi-condition rule on THREE AI fields

Adding a rule = adding a subclass (Open/Closed). RuleEngine treats every rule the same way
(Liskov Substitution / polymorphism): it never checks which kind of rule it is running.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List

from ..config import RuleSettings
from ..models import OTHER_LANGUAGE, AIAnalysis, Outcome, Utterance


class Rule(ABC):
    """One business rule. Subclasses decide *when* it fires; the base class fixes the contract."""

    #: the outcome a firing rule argues for
    outcome: Outcome

    def __init__(self, settings: RuleSettings):
        self._settings = settings

    @abstractmethod
    def reasons(self, utterance: Utterance, analysis: AIAnalysis) -> List[str]:
        """Human-readable reasons the rule fired. An empty list means it did not fire."""

    def fires(self, utterance: Utterance, analysis: AIAnalysis) -> bool:
        return bool(self.reasons(utterance, analysis))


class RejectRule(Rule):
    outcome = Outcome.REJECT

    def reasons(self, utterance, analysis):
        found = []
        if not analysis.translation.strip():
            found.append("empty translation")
        if analysis.detected_language == OTHER_LANGUAGE:
            found.append("language is not English, Indonesian or Chinese")
        return found


class ConfidenceCheckRule(Rule):
    outcome = Outcome.CHECK

    def reasons(self, utterance, analysis):
        found = []
        if analysis.language_confidence < self._settings.min_language_confidence:
            found.append("low language confidence (%.2f)" % analysis.language_confidence)
        if analysis.translation_confidence < self._settings.min_translation_confidence:
            found.append("low translation confidence (%.2f)" % analysis.translation_confidence)
        return found


class LanguageMismatchRule(Rule):
    outcome = Outcome.CHECK

    def reasons(self, utterance, analysis):
        expected = utterance.speaker.language.value
        if expected != analysis.detected_language:
            return ["%s is set to %s but the AI heard %s" % (utterance.speaker.name, expected, analysis.detected_language)]
        return []


class TensionRule(Rule):
    """The multi-condition rule: tone AND intensity AND tone confidence must all be met."""

    outcome = Outcome.TENSION

    def reasons(self, utterance, analysis):
        s = self._settings
        if (analysis.tone in s.tension_tones
                and analysis.intensity >= s.tension_min_intensity
                and analysis.tone_confidence >= s.tension_min_tone_confidence):
            return ["%s tone (confidence %.2f) at intensity %d"
                    % (analysis.tone.value, analysis.tone_confidence, analysis.intensity)]
        return []


class RuleEngine:
    """Runs a list of rules and groups what fired by outcome."""

    def __init__(self, rules: Iterable[Rule]):
        self._rules = list(rules)

    @classmethod
    def default(cls, settings: RuleSettings) -> "RuleEngine":
        return cls([RejectRule(settings), ConfidenceCheckRule(settings),
                    LanguageMismatchRule(settings), TensionRule(settings)])

    def evaluate(self, utterance: Utterance, analysis: AIAnalysis) -> Dict[Outcome, List[str]]:
        findings: Dict[Outcome, List[str]] = {outcome: [] for outcome in Outcome}
        for rule in self._rules:
            findings[rule.outcome].extend(rule.reasons(utterance, analysis))
        return findings
