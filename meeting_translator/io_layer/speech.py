"""Speech-to-text: turns a recording of one spoken sentence into text.

It belongs to the IO layer (it is an input boundary). The AI never receives audio: the recording is
transcribed on this computer and only the TEXT goes on to the AIManager.

    SpeechTranscriber (interface)  <-  WhisperTranscriber (faster-whisper, runs locally on the CPU)
                                   <-  any other engine, or a fake in the tests
"""

from __future__ import annotations

import io
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional, Tuple

from ..exceptions import SpeechError, SpeechUnavailableError, TranscriptionError
from ..models import Language

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # the largest recording we will transcribe
AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".aac")


@dataclass(frozen=True)
class Transcription:
    """The result of transcribing one recording."""

    text: str
    language: Optional[Language] = None  # language used or detected; None if it is not one of the three

    @property
    def is_empty(self) -> bool:
        """True when no speech was found (silence, noise)."""
        return not self.text.strip()


class SpeechTranscriber(ABC):
    """Interface (Dependency Inversion): the IO layer and the GUI depend on this contract, not on Whisper."""

    @abstractmethod
    def transcribe(self, audio: bytes, language: Optional[Language] = None,
                   allowed_languages: Optional[Iterable[Language]] = None) -> Transcription:
        """Turn the bytes of a recording (wav, mp3, ...) into text.

        `language` is the language the speaker is expected to use (a hint that makes the result
        more accurate); None means 'work it out' (optionally restricted to `allowed_languages`).
        Raises a SpeechError subclass on failure.
        """


class WhisperTranscriber(SpeechTranscriber):
    """Local speech recognition with faster-whisper.

    The (large) model is loaded lazily on first use, once per model name for the whole process, and
    shared by every instance: Streamlit re-creates objects often and reloading would be very slow.
    """

    WHISPER_CODES: Dict[Language, str] = {
        Language.ENGLISH: "en", Language.INDONESIAN: "id", Language.CHINESE: "zh"}
    _LANGUAGE_BY_CODE: Dict[str, Language] = {code: language for language, code in WHISPER_CODES.items()}

    _shared_models: Dict[str, object] = {}  # model name -> loaded model
    _load_lock = threading.Lock()           # two threads must not load the same model twice
    _run_lock = threading.Lock()            # CPU-bound and the model is shared: one recording at a time

    def __init__(self, model_name: str = "base", model_loader: Optional[Callable[[str], object]] = None):
        """`model_loader` lets tests plug in a fake model instead of downloading a real one."""
        self._model_name = model_name
        self._loader = model_loader or self._load_faster_whisper
        self._models = self._shared_models if model_loader is None else {}

    @property
    def model_name(self) -> str:
        return self._model_name

    # ----- model -----
    @staticmethod
    def _load_faster_whisper(name: str):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise SpeechUnavailableError("Speech-to-text is not installed. Run: pip install faster-whisper")
        return WhisperModel(name, device="cpu", compute_type="int8")  # int8 = compressed, faster on a CPU

    def _model(self):
        with self._load_lock:
            if self._model_name not in self._models:
                try:
                    self._models[self._model_name] = self._loader(self._model_name)
                except SpeechUnavailableError:
                    raise
                except Exception as error:  # noqa: BLE001 - e.g. the model download failed
                    logging.error("Could not load speech model %s: %s", self._model_name, error)
                    raise SpeechUnavailableError(
                        "Could not load the speech model '%s' (%s). The first run needs internet to download it."
                        % (self._model_name, error))
            return self._models[self._model_name]

    MIN_ALLOWED_PROBABILITY = 0.25
    MIN_ALLOWED_MARGIN = 0.10

    # ----- transcription -----
    @staticmethod
    def pick_supported(language_probabilities: Optional[Iterable[Tuple[str, float]]],
                       allowed_languages: Optional[Iterable[Language]] = None) -> Optional[str]:
        """From Whisper's (code, probability) pairs choose the likeliest supported language.
        When `allowed_languages` is provided, only those languages are considered and a minimum
        confidence/margin is required so uncertain clips are not misattributed.
        """
        if allowed_languages is not None:
            allowed_codes = {
                WhisperTranscriber.WHISPER_CODES[lang]
                for lang in allowed_languages
                if lang in WhisperTranscriber.WHISPER_CODES
            }
        else:
            allowed_codes = set(WhisperTranscriber._LANGUAGE_BY_CODE)

        ranked = sorted(
            ((code, prob) for code, prob in (language_probabilities or []) if code in allowed_codes),
            key=lambda item: item[1],
            reverse=True,
        )
        if not ranked:
            return None
        best_code, best_prob = ranked[0]
        if allowed_languages is not None:
            second_prob = ranked[1][1] if len(ranked) > 1 else 0.0
            if best_prob < WhisperTranscriber.MIN_ALLOWED_PROBABILITY:
                return None
            if len(allowed_codes) > 1 and (best_prob - second_prob) < WhisperTranscriber.MIN_ALLOWED_MARGIN:
                return None
        return best_code

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in text)

    @staticmethod
    def _run(model, audio: bytes, code: Optional[str]):
        """One pass over the audio. Must consume the segment generator. Returns (text, info)."""
        segments, info = model.transcribe(io.BytesIO(audio), language=code, beam_size=5,
                                          temperature=0.0, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip(), info

    def transcribe(self, audio: bytes, language: Optional[Language] = None,
                   allowed_languages: Optional[Iterable[Language]] = None) -> Transcription:
        if not audio:
            raise TranscriptionError("The recording is empty.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise TranscriptionError("The recording is larger than %d MB. Record a shorter sentence."
                                     % (MAX_AUDIO_BYTES // (1024 * 1024)))
        model = self._model()
        hint = self.WHISPER_CODES.get(language)
        allowed_set = set(allowed_languages) if allowed_languages is not None else None
        try:
            with self._run_lock:
                text, info = self._run(model, audio, hint)
                used = hint or getattr(info, "language", None)
                if hint is None:  # auto-detect, restricted to supported (or meeting) languages
                    probs = getattr(info, "all_language_probs", None)
                    best = self.pick_supported(probs, allowed_languages=allowed_set)
                    if best is None and allowed_set is not None and probs is not None:
                        used = None  # uncertain among meeting languages; do not guess
                    elif best is not None and best != used:  # e.g. Whisper said Malay; we only know Indonesian
                        text, info = self._run(model, audio, best)
                        used = best
                    if used is None and (allowed_set is None or Language.CHINESE in allowed_set) and self._contains_cjk(text):
                        used = self.WHISPER_CODES[Language.CHINESE]
        except SpeechError:
            raise
        except Exception as error:  # noqa: BLE001 - corrupt or unsupported audio, etc.
            logging.warning("Transcription failed: %s", error)
            raise TranscriptionError("Could not transcribe that recording (%s)." % error)
        detected_language = self._LANGUAGE_BY_CODE.get(used)
        if allowed_set is not None and detected_language not in allowed_set:
            detected_language = None
        return Transcription(text, detected_language)
