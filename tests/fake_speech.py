"""Fake speech components: tests never load Whisper, download a model or need a microphone."""

import io
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from meeting_translator.io_layer import SpeechTranscriber, Transcription
from meeting_translator.models import Language


class FakeTranscriber(SpeechTranscriber):
    """Fake speech-to-text: returns the queued Transcriptions in order. An Exception in the queue is raised.
    Once the queue is down to one entry, that entry repeats. Every call is recorded in `calls`."""

    def __init__(self, *results):
        self.results = list(results) or [Transcription("hello", Language.ENGLISH)]
        self.calls: List[Tuple[bytes, Optional[Language]]] = []
        self.allowed_calls: List[Optional[Tuple[Language, ...]]] = []

    def transcribe(self, audio: bytes, language: Optional[Language] = None,
                   allowed_languages: Optional[Iterable[Language]] = None) -> Transcription:
        self.calls.append((audio, language))
        self.allowed_calls.append(tuple(allowed_languages) if allowed_languages is not None else None)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


class FakeSegment:
    def __init__(self, text: str):
        self.text = text


class FakeInfo:
    def __init__(self, language: str, all_language_probs=None):
        self.language = language
        self.all_language_probs = all_language_probs


class FakeWhisperModel:
    """Stands in for faster_whisper.WhisperModel.

    `texts_by_language` maps the `language` option of a pass (None = auto-detect) to the segment texts it
    returns; `texts` is the default. `calls` records the options of every pass and the audio it received.
    """

    def __init__(self, texts: Sequence[str] = (" Hello ", "there "), language: str = "en", probabilities=None,
                 texts_by_language: Optional[Dict[Optional[str], Sequence[str]]] = None, error: Optional[Exception] = None):
        self.texts = texts
        self.language = language
        self.probabilities = probabilities
        self.texts_by_language = texts_by_language or {}
        self.error = error
        self.calls: List[dict] = []

    def transcribe(self, audio_file, **options):
        self.calls.append({**options, "audio": audio_file.read() if isinstance(audio_file, io.BytesIO) else audio_file})
        if self.error is not None:
            raise self.error
        texts = self.texts_by_language.get(options.get("language"), self.texts)
        return iter([FakeSegment(text) for text in texts]), FakeInfo(self.language, self.probabilities)
