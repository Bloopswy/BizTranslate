"""Configuration: application settings (from the environment) and business-rule settings
(from an optional JSON file, so thresholds can be tuned without touching code)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Tuple

from .exceptions import ValidationError
from .models import Tone


@dataclass(frozen=True)
class RuleSettings:
    """Thresholds used by the business rules. Immutable, so rules can share one instance safely."""

    tension_tones: Tuple[Tone, ...] = (Tone.ANGRY, Tone.FRUSTRATED, Tone.ANXIOUS)
    tension_min_intensity: int = 4
    tension_min_tone_confidence: float = 0.7
    min_language_confidence: float = 0.6
    min_translation_confidence: float = 0.6
    context_sentences: int = 3  # earlier sentences shown to the user and sent to the AI as context

    @classmethod
    def from_dict(cls, data: dict) -> "RuleSettings":
        """Build from a dict, ignoring unknown keys. Raises ValidationError on bad values."""
        if not isinstance(data, dict):
            raise ValidationError("rule settings must be a JSON object")
        defaults = cls()
        try:
            tones = tuple(Tone(t) for t in data.get("tension_tones", [t.value for t in defaults.tension_tones]))
            intensity = data.get("tension_min_intensity", defaults.tension_min_intensity)
            context = data.get("context_sentences", defaults.context_sentences)
            confidences = {key: data.get(key, getattr(defaults, key)) for key in (
                "tension_min_tone_confidence", "min_language_confidence", "min_translation_confidence")}
        except (ValueError, TypeError) as error:
            raise ValidationError("invalid rule settings: %s" % error)
        if isinstance(intensity, bool) or not isinstance(intensity, int) or not 1 <= intensity <= 5:
            raise ValidationError("tension_min_intensity must be a whole number from 1 to 5")
        if isinstance(context, bool) or not isinstance(context, int) or not 0 <= context <= 6:
            raise ValidationError("context_sentences must be a whole number from 0 to 6")
        for key, value in confidences.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                raise ValidationError("%s must be a number from 0.0 to 1.0" % key)
        return cls(tension_tones=tones, tension_min_intensity=intensity, context_sentences=context,
                   **{key: float(value) for key, value in confidences.items()})

    @classmethod
    def load(cls, path: str) -> "RuleSettings":
        """Load settings from a JSON file. A missing file means defaults; an unreadable or invalid
        file is logged and defaults are used (the application keeps working)."""
        if not path or not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return cls.from_dict(json.load(handle))
        except (OSError, ValueError, ValidationError) as error:
            logging.error("Ignoring rule settings %s (%s); using defaults", path, error)
            return cls()


class Settings:
    """Application settings read from environment variables (and an optional .env file)."""

    DEFAULT_MODEL = "gemma-4-26b-a4b-it"
    DEFAULT_WHISPER_MODEL = "base"

    def __init__(self, env: Dict[str, str]):
        self._env = env

    @classmethod
    def from_environment(cls, env_file: str = ".env") -> "Settings":
        """Variables already set in the environment win over the .env file."""
        merged = dict(cls._read_env_file(env_file))
        merged.update(os.environ)
        return cls(merged)

    @staticmethod
    def _read_env_file(path: str) -> Dict[str, str]:
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                lines = handle.read().splitlines()
        except (OSError, UnicodeDecodeError):
            return {}
        values = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and value:
                values[key] = value
        return values

    def items(self) -> tuple:
        """The settings as a sorted, hashable tuple of (name, value) pairs."""
        return tuple(sorted(self._env.items()))

    @property
    def api_key(self) -> str:
        return self._env.get("GEMINI_API_KEY", "").strip()

    @property
    def model(self) -> str:
        return self._env.get("GEMMA_MODEL", self.DEFAULT_MODEL)

    @property
    def whisper_model(self) -> str:
        """Speech-to-text model size: tiny / base / small / medium (bigger = more accurate, slower)."""
        return self._env.get("WHISPER_MODEL", self.DEFAULT_WHISPER_MODEL).strip() or self.DEFAULT_WHISPER_MODEL

    @property
    def data_path(self) -> str:
        return self._env.get("DATA_FILE", os.path.join("data", "records.json"))

    @property
    def log_path(self) -> str:
        return self._env.get("LOG_FILE", os.path.join("data", "app.log"))

    @property
    def input_dir(self) -> str:
        return self._env.get("INPUT_DIR", "input")

    @property
    def report_dir(self) -> str:
        return self._env.get("REPORT_DIR", os.path.join("data", "reports"))

    @property
    def rules_path(self) -> str:
        return self._env.get("RULES_FILE", os.path.join("config", "rules.json"))
