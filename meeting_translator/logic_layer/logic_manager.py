"""LogicManager: applies the domain rules to AI-enriched sentences.

Outcomes:
  TENSION - a heated moment (negative tone, strong, and the AI is confident): both sides
            should slow down and confirm understanding
  CHECK   - the translation may be unreliable (low confidence, or the speaker used a
            different language than expected): confirm with the speaker
  ACCEPT  - clear and routine
  REJECT  - unusable (empty translation or unsupported language)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..config import RuleSettings
from ..models import AIAnalysis, Decision, Outcome, Utterance
from .rules import RuleEngine
from .scoring import ScoringStrategy, ToneIntensityScoring


class LogicManager:
    """evaluate -> score -> route.

    The rule engine is created and owned here (composition). A different scoring strategy or a
    custom engine can be supplied without changing this class (Open/Closed, Dependency Inversion).
    """

    def __init__(self, settings: Optional[RuleSettings] = None, engine: Optional[RuleEngine] = None,
                 scoring: Optional[ScoringStrategy] = None):
        self._settings = settings or RuleSettings()
        self._engine = engine or RuleEngine.default(self._settings)
        self._scoring = scoring or ToneIntensityScoring()

    @property
    def settings(self) -> RuleSettings:
        return self._settings

    def evaluate(self, utterance: Utterance, analysis: AIAnalysis) -> Dict[Outcome, List[str]]:
        """Which rules fired, grouped by the outcome they argue for."""
        return self._engine.evaluate(utterance, analysis)

    def score(self, analysis: AIAnalysis) -> int:
        return self._scoring.score(analysis)

    def route(self, utterance: Utterance, analysis: AIAnalysis) -> Decision:
        """Decide the final outcome: REJECT beats TENSION beats CHECK beats ACCEPT."""
        findings = self.evaluate(utterance, analysis)
        if findings[Outcome.REJECT]:
            return Decision(Outcome.REJECT, 0, tuple(findings[Outcome.REJECT]))
        points = self.score(analysis)
        if findings[Outcome.TENSION]:  # tension wins, but still reports any translation doubts
            return Decision(Outcome.TENSION, points, tuple(findings[Outcome.TENSION] + findings[Outcome.CHECK]))
        if findings[Outcome.CHECK]:
            return Decision(Outcome.CHECK, points, tuple(findings[Outcome.CHECK]))
        return Decision(Outcome.ACCEPT, points, ("clear and routine",))
