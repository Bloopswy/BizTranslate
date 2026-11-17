"""Shared builders for tests (models only - no AI, storage or IO needed)."""

import os
import tempfile

from meeting_translator.models import (AIAnalysis, Decision, Language, MeetingSetup, Outcome, Party,
                                       ProcessedRecord, Utterance)


def make_setup(meeting="m1"):
    return MeetingSetup(meeting, Party("Acme", Language.ENGLISH), Party("Mitra", Language.INDONESIAN))


def good_ai_dict(**overrides):
    fields = {
        "detected_language": "English", "language_confidence": 0.95,
        "translation": "Selamat pagi", "translation_confidence": 0.9,
        "tone": "neutral", "tone_confidence": 0.9, "intensity": 2, "tone_reason": "Tenang.",
    }
    fields.update(overrides)
    return fields


def good_ai(**overrides):
    return AIAnalysis.from_dict(good_ai_dict(**overrides))


def utterance(text="Good morning", speaker="A", timestamp="2026-10-14T09:00:00+00:00", position="", setup=None):
    return Utterance.create(setup or make_setup(), speaker, text, timestamp, "text", position)


def saved(seq, text="hi", meeting="m1", speaker="A", outcome=Outcome.ACCEPT, score=20, **ai_overrides):
    """A fully processed record, as stored."""
    u = utterance(text, speaker, "2026-10-14T09:%02d:00+00:00" % seq, position=seq, setup=make_setup(meeting))
    return ProcessedRecord(u, good_ai(**ai_overrides), Decision(outcome, score, ("clear and routine",)), seq)


class TempDir:
    """Context manager giving a temporary folder."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        return self._dir.name

    def __exit__(self, *exc):
        self._dir.cleanup()
        return False

    @staticmethod
    def join(folder, *parts):
        return os.path.join(folder, *parts)
