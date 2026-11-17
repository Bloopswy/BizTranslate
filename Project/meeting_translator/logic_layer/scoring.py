from __future__ import annotations
from abc import ABC, abstractmethod
from ..models import AIAnalysis, Tone

class ScoringStrategy(ABC):
    """Interface: turn an AI analysis into a 0-100 attention score."""

    @abstractmethod
    def score(self, analysis: AIAnalysis) -> int:
        """Return an integer from 0 to 100."""


class ToneIntensityScoring(ScoringStrategy):
    """Intensity (10-50) plus a weight for the tone, capped at 100."""

    TONE_WEIGHT = {
        Tone.ANGRY: 30, Tone.FRUSTRATED: 25, Tone.ANXIOUS: 20, Tone.URGENT: 15,
        Tone.SAD: 10, Tone.NEUTRAL: 0, Tone.HAPPY: 0, Tone.GRATEFUL: 0,
    }

    def score(self, analysis: AIAnalysis) -> int:
        points = analysis.intensity * 10 + self.TONE_WEIGHT.get(analysis.tone, 0)
        return max(0, min(100, points))
