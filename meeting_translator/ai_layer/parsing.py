"""Turning the model's raw text into a validated AIAnalysis."""

from __future__ import annotations

import json
from typing import Any

from ..exceptions import AIResponseError
from ..models import DETECTED_LANGUAGES, AIAnalysis, Tone


class ResponseParser:
    """Pulls the JSON object out of the model text."""

    def parse(self, raw_text: Any) -> dict:
        """Tolerates markdown fences and a sentence before/after the object.
        Raises AIResponseError if no JSON object can be found."""
        if not isinstance(raw_text, str):
            raise AIResponseError("response is not text")
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start == -1 or end <= start:
            raise AIResponseError("no JSON object in the response")
        try:
            data = json.loads(raw_text[start:end + 1])
        except ValueError as error:
            raise AIResponseError("invalid JSON: %s" % error)
        if not isinstance(data, dict):
            raise AIResponseError("JSON is not an object")
        return data


class ResponseValidator:
    """Enforces the response contract exactly; nothing unvalidated reaches the logic layer."""

    CONFIDENCE_KEYS = ("language_confidence", "translation_confidence", "tone_confidence")

    @staticmethod
    def _is_number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def validate(self, data: Any) -> AIAnalysis:
        """Return an AIAnalysis, or raise AIResponseError naming the first problem."""
        if not isinstance(data, dict):
            raise AIResponseError("response is not an object")
        if data.get("detected_language") not in DETECTED_LANGUAGES:
            raise AIResponseError("detected_language is not one of %s" % DETECTED_LANGUAGES)
        if data.get("tone") not in Tone.values():
            raise AIResponseError("tone is not one of %s" % Tone.values())
        for key in self.CONFIDENCE_KEYS:
            value = data.get(key)
            if not self._is_number(value) or not 0.0 <= value <= 1.0:
                raise AIResponseError("%s must be a number from 0.0 to 1.0" % key)
        intensity = data.get("intensity")
        if isinstance(intensity, bool) or not isinstance(intensity, int) or not 1 <= intensity <= 5:
            raise AIResponseError("intensity must be a whole number from 1 to 5")
        for key in ("translation", "tone_reason"):
            if not isinstance(data.get(key), str):
                raise AIResponseError("%s must be text" % key)
        return AIAnalysis.from_dict(data)
