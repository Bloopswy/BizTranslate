"""Domain model: the objects that flow through the four managers.

    MeetingSetup  o-- Party (A)        aggregation: parties exist independently of a meeting
                  o-- Party (B)
    Utterance     --> Party            association: an utterance refers to its speaker/listener
    ProcessedRecord *-- Utterance      composition: a record owns its parts; they are created
                    *-- AIAnalysis     for it and never shared between records
                    *-- Decision
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .exceptions import RecordFormatError, ValidationError

MAX_SENTENCE_CHARS = 2000
MAX_NAME_CHARS = 40
MAX_MEETING_CHARS = 60
OTHER_LANGUAGE = "Other"  # what the AI reports for a language we do not support
LEGACY_MEETING = "earlier-records"


class Language(str, Enum):
    ENGLISH = "English"
    INDONESIAN = "Indonesian"
    CHINESE = "Chinese"

    @classmethod
    def values(cls) -> List[str]:
        return [member.value for member in cls]

    @classmethod
    def parse(cls, value, default: Optional["Language"] = None) -> "Language":
        """The matching Language, or `default`; raises ValidationError if no default."""
        try:
            return cls(value)
        except ValueError:
            if default is not None:
                return default
            raise ValidationError("language must be one of: " + ", ".join(cls.values()))


DETECTED_LANGUAGES = Language.values() + [OTHER_LANGUAGE]


class Tone(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    GRATEFUL = "grateful"
    SAD = "sad"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    URGENT = "urgent"

    @classmethod
    def values(cls) -> List[str]:
        return [member.value for member in cls]


class Outcome(str, Enum):
    TENSION = "TENSION"
    CHECK = "CHECK"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"

    @classmethod
    def parse(cls, value) -> "Outcome":
        legacy = {"ESCALATE": cls.TENSION, "REVIEW": cls.CHECK}  # names used by older versions
        if value in legacy:
            return legacy[value]
        try:
            return cls(value)
        except ValueError:
            raise RecordFormatError("unknown outcome %r" % (value,))


class TextCleaner:
    """Tidy user-supplied text (names are put into prompts, so keep them short and single-line)."""

    @staticmethod
    def label(text, fallback: str, limit: int) -> str:
        if not isinstance(text, str):
            return fallback
        cleaned = " ".join(text.split())
        cleaned = "".join(ch for ch in cleaned if ch.isprintable())[:limit].strip()
        return cleaned or fallback


class Party:
    """One side of the meeting: a name and the language that side speaks."""

    def __init__(self, name: str, language):
        self._name = TextCleaner.label(name, "Party", MAX_NAME_CHARS)
        self._language = Language.parse(language)

    @property
    def name(self) -> str:
        return self._name

    @property
    def language(self) -> Language:
        return self._language

    def describe(self) -> str:
        return "%s (%s)" % (self._name, self._language.value)

    def to_dict(self) -> Dict[str, str]:
        return {"name": self._name, "language": self._language.value}

    def __eq__(self, other) -> bool:
        return isinstance(other, Party) and (self._name, self._language) == (other._name, other._language)

    def __hash__(self) -> int:
        return hash((self._name, self._language))

    def __repr__(self) -> str:
        return "Party(%r, %r)" % (self._name, self._language.value)


class MeetingSetup:
    """A meeting name plus its two parties. The parties are passed in (aggregation)."""

    PARTY_IDS = ("A", "B")

    def __init__(self, meeting: str, party_a: Party, party_b: Party):
        self._meeting = TextCleaner.label(meeting, self.default_meeting_name(), MAX_MEETING_CHARS)
        self._parties = {"A": party_a, "B": party_b}

    @staticmethod
    def default_meeting_name() -> str:
        return "meeting-" + datetime.now().strftime("%Y-%m-%d")

    @classmethod
    def default(cls) -> "MeetingSetup":
        return cls(cls.default_meeting_name(), Party("Party A", Language.ENGLISH), Party("Party B", Language.INDONESIAN))

    @classmethod
    def from_dict(cls, raw, fallback: Optional["MeetingSetup"] = None) -> "MeetingSetup":
        """Tolerant parse: any bad or missing value falls back to `fallback` (or the defaults)."""
        base = fallback if fallback is not None else cls.default()
        raw = raw if isinstance(raw, dict) else {}
        parties_raw = raw.get("parties") if isinstance(raw.get("parties"), dict) else {}
        parties = {}
        for party_id in cls.PARTY_IDS:
            party_raw = parties_raw.get(party_id) if isinstance(parties_raw.get(party_id), dict) else {}
            base_party = base.party(party_id)
            parties[party_id] = Party(
                TextCleaner.label(party_raw.get("name"), base_party.name, MAX_NAME_CHARS),
                Language.parse(party_raw.get("language"), default=base_party.language),
            )
        return cls(TextCleaner.label(raw.get("meeting"), base.meeting, MAX_MEETING_CHARS), parties["A"], parties["B"])

    @property
    def meeting(self) -> str:
        return self._meeting

    def party(self, party_id: str) -> Party:
        return self._parties[party_id]

    @staticmethod
    def other_party_id(party_id: str) -> str:
        return "B" if party_id == "A" else "A"

    def listener_of(self, speaker_id: str) -> Party:
        return self._parties[self.other_party_id(speaker_id)]

    def party_for_language(self, language: Optional[Language]) -> Optional[str]:
        """The party id ('A' or 'B') that uniquely speaks `language`, or None if neither matches
        or both parties share that language."""
        if language is None:
            return None
        matches = [pid for pid in self.PARTY_IDS if self._parties[pid].language == language]
        return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class Utterance:
    """One spoken (or typed) sentence, before any AI processing."""

    id: str
    meeting: str
    timestamp: str
    speaker_id: str
    speaker: Party
    listener: Party
    transcript: str
    input_type: str = "text"

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def valid_timestamp(value) -> str:
        """The timestamp text if it is valid ISO 8601, else ''."""
        if not isinstance(value, str):
            return ""
        try:
            datetime.fromisoformat(value.strip())
        except ValueError:
            return ""
        return value.strip()

    @staticmethod
    def make_id(meeting: str, timestamp: str, position, speaker_id: str, transcript: str) -> str:
        """Same sentence in the same meeting always gets the same id, so re-reading a file
        never duplicates it. `position` (a line number) tells apart repeated sentences."""
        key = "|".join([meeting, timestamp, str(position), speaker_id, transcript])
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def create(cls, setup: MeetingSetup, speaker_id, transcript, timestamp=None,
               input_type: str = "text", position="") -> "Utterance":
        """Validate and build an utterance. timestamp=None means 'now'. Raises ValidationError."""
        speaker_id = speaker_id.strip().upper() if isinstance(speaker_id, str) else ""
        if speaker_id not in MeetingSetup.PARTY_IDS:
            raise ValidationError("speaker must be A or B")
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValidationError("missing or empty sentence")
        text = transcript.strip()
        if len(text) > MAX_SENTENCE_CHARS:
            raise ValidationError("sentence longer than %d characters" % MAX_SENTENCE_CHARS)
        when = cls.now_iso() if timestamp is None else cls.valid_timestamp(timestamp)
        return cls(
            id=cls.make_id(setup.meeting, when, position, speaker_id, text),
            meeting=setup.meeting, timestamp=when, speaker_id=speaker_id,
            speaker=setup.party(speaker_id), listener=setup.listener_of(speaker_id),
            transcript=text, input_type=input_type,
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id, "meeting": self.meeting, "timestamp": self.timestamp, "speaker": self.speaker_id,
            "speaker_name": self.speaker.name, "speaker_language": self.speaker.language.value,
            "listener_name": self.listener.name, "target_language": self.listener.language.value,
            "transcript": self.transcript, "input_type": self.input_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Utterance":
        try:
            return cls(
                id=str(data["id"]), meeting=str(data.get("meeting") or LEGACY_MEETING),
                timestamp=str(data.get("timestamp", "")), speaker_id=str(data.get("speaker", "?")),
                speaker=Party(data.get("speaker_name", "Earlier record"),
                              Language.parse(data.get("speaker_language"), default=Language.ENGLISH)),
                listener=Party(data.get("listener_name", "Listener"),
                               Language.parse(data.get("target_language"), default=Language.ENGLISH)),
                transcript=str(data["transcript"]), input_type=str(data.get("input_type", "text")),
            )
        except (KeyError, TypeError) as error:
            raise RecordFormatError("bad utterance data: %r" % (error,))


@dataclass(frozen=True)
class AIAnalysis:
    """The validated fields the AI returns for one sentence."""

    detected_language: str
    language_confidence: float
    translation: str
    translation_confidence: float
    tone: Tone
    tone_confidence: float
    intensity: int
    tone_reason: str

    def to_dict(self) -> dict:
        return {
            "detected_language": self.detected_language, "language_confidence": self.language_confidence,
            "translation": self.translation, "translation_confidence": self.translation_confidence,
            "tone": self.tone.value, "tone_confidence": self.tone_confidence,
            "intensity": self.intensity, "tone_reason": self.tone_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AIAnalysis":
        """Build from already-validated or stored data (the AI layer does the strict validation)."""
        try:
            return cls(
                detected_language=str(data["detected_language"]),
                language_confidence=float(data["language_confidence"]),
                translation=str(data["translation"]),
                translation_confidence=float(data["translation_confidence"]),
                tone=Tone(data["tone"]), tone_confidence=float(data["tone_confidence"]),
                intensity=int(data["intensity"]), tone_reason=str(data.get("tone_reason", "")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RecordFormatError("bad AI fields: %r" % (error,))


@dataclass(frozen=True)
class Decision:
    """What the logic layer decided: outcome, attention score and the reasons behind it."""

    outcome: Outcome
    score: int
    reasons: Tuple[str, ...]


class ProcessedRecord:
    """An utterance together with its AI analysis and the logic decision (what gets stored)."""

    def __init__(self, utterance: Utterance, analysis: AIAnalysis, decision: Decision, seq: int = 0):
        self._utterance = utterance
        self._analysis = analysis
        self._decision = decision
        self._seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else 0

    # ----- parts -----
    @property
    def utterance(self) -> Utterance:
        return self._utterance

    @property
    def analysis(self) -> AIAnalysis:
        return self._analysis

    @property
    def decision(self) -> Decision:
        return self._decision

    def with_seq(self, seq: int) -> "ProcessedRecord":
        return ProcessedRecord(self._utterance, self._analysis, self._decision, seq)

    # ----- convenient read-only views used by queries, formatters and reports -----
    @property
    def id(self) -> str:
        return self._utterance.id

    @property
    def meeting(self) -> str:
        return self._utterance.meeting

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def timestamp(self) -> str:
        return self._utterance.timestamp

    @property
    def speaker_name(self) -> str:
        return self._utterance.speaker.name

    @property
    def speaker_language(self) -> str:
        return self._utterance.speaker.language.value

    @property
    def listener_name(self) -> str:
        return self._utterance.listener.name

    @property
    def target_language(self) -> str:
        return self._utterance.listener.language.value

    @property
    def transcript(self) -> str:
        return self._utterance.transcript

    @property
    def translation(self) -> str:
        return self._analysis.translation

    @property
    def detected_language(self) -> str:
        return self._analysis.detected_language

    @property
    def tone(self) -> str:
        return self._analysis.tone.value

    @property
    def intensity(self) -> int:
        return self._analysis.intensity

    @property
    def outcome(self) -> str:
        return self._decision.outcome.value

    @property
    def score(self) -> int:
        return self._decision.score

    @property
    def reasons(self) -> List[str]:
        return list(self._decision.reasons)

    # ----- (de)serialisation: the flat dict is the stored format -----
    def to_dict(self) -> dict:
        data = {**self._utterance.to_dict(), **self._analysis.to_dict()}
        data.update({"outcome": self.outcome, "score": self.score, "reasons": self.reasons, "seq": self._seq})
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessedRecord":
        """Rebuild a record from stored data, upgrading records saved by older versions.
        Raises RecordFormatError if the data cannot be understood."""
        if not isinstance(data, dict):
            raise RecordFormatError("a record must be an object")
        data = dict(data)
        if "translation" not in data and "english_translation" in data:
            data["translation"] = data.pop("english_translation")
        if "intensity" not in data and "urgency" in data:
            data["intensity"] = data.pop("urgency")
        reasons = data.get("reasons", [])
        if not isinstance(reasons, (list, tuple)):
            raise RecordFormatError("reasons must be a list")
        try:
            score = int(data["score"])
        except (KeyError, TypeError, ValueError):
            raise RecordFormatError("score is missing or not a number")
        decision = Decision(Outcome.parse(data.get("outcome")), score, tuple(str(r) for r in reasons))
        try:
            seq = int(data.get("seq", 0))  # CSV stores numbers as text
        except (TypeError, ValueError):
            seq = 0
        return cls(Utterance.from_dict(data), AIAnalysis.from_dict(data), decision, seq)


class ClockFormatter:
    """Turns stored ISO timestamps into readable clock times."""

    @staticmethod
    def format(timestamp, tz_name: Optional[str] = None, with_date: bool = False) -> str:
        """'14:32:05' (or with the date) in the given IANA zone, else the computer's zone.
        Naive times are taken as UTC. Unreadable times show '--:--:--'."""
        try:
            moment = datetime.fromisoformat(timestamp)
        except (TypeError, ValueError):
            return "--:--:--"
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        try:
            if tz_name:
                from zoneinfo import ZoneInfo
                moment = moment.astimezone(ZoneInfo(tz_name))
            else:
                moment = moment.astimezone()
        except Exception:  # unknown zone, or tzdata not installed: fall back to UTC
            moment = moment.astimezone(timezone.utc)
        return moment.strftime("%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S")
