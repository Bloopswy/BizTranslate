"""Reading meeting files (.json / .txt) into validated utterances.

    MeetingFileParser (abstract base)
      |- JsonMeetingParser
      '- TextMeetingParser
MeetingFileReader picks the parser by extension - no if/elif on the file type (polymorphism).
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..exceptions import ValidationError
from ..models import MeetingSetup, Utterance


@dataclass
class ParseResult:
    utterances: List[Utterance] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class MeetingFileParser(ABC):
    """Turns file content into (position, speaker, timestamp, transcript) items, then utterances."""

    @abstractmethod
    def _items(self, short_name: str, content: str, setup: MeetingSetup, errors: List[str]):
        """Return (setup, items); items are (position, speaker, timestamp, transcript).
        Append human-readable problems to `errors`. Never raise."""

    def parse(self, name: str, content: str, setup: MeetingSetup) -> ParseResult:
        result = ParseResult()
        short_name = os.path.basename(name)
        setup, items = self._items(short_name, content, setup, result.errors)
        for position, speaker, timestamp, transcript in items:
            try:
                result.utterances.append(
                    Utterance.create(setup, speaker, transcript, timestamp or "", "file", position))
            except ValidationError as error:
                result.errors.append("%s item %d skipped: %s" % (short_name, position, error))
        return result


class JsonMeetingParser(MeetingFileParser):
    """An object {"meeting", "parties", "utterances": [...]} or just the list of utterances."""

    def _items(self, short_name, content, setup, errors):
        try:
            data = json.loads(content)
        except ValueError as error:
            errors.append("%s is not valid JSON: %s" % (short_name, error))
            return setup, []
        if isinstance(data, dict):
            setup = MeetingSetup.from_dict(data, setup)
            data = data.get("utterances")
        if not isinstance(data, list):
            errors.append("%s must contain a list of utterances (or an object with an 'utterances' list)" % short_name)
            return setup, []
        items = []
        for position, item in enumerate(data, start=1):
            if isinstance(item, dict):
                items.append((position, item.get("speaker"), item.get("timestamp", ""), item.get("transcript")))
            else:
                errors.append("%s item %d skipped: not an object" % (short_name, position))
        return setup, items


class TextMeetingParser(MeetingFileParser):
    """One sentence per line:  A: text   or   [2026-10-14T09:00:05+08:00] B: text"""

    LINE = re.compile(r"^\s*(?:\[(?P<time>[^\]]*)\]\s*)?(?P<speaker>[AaBb])\s*[:\uFF1A]\s*(?P<text>.*\S)\s*$")

    def _items(self, short_name, content, setup, errors):
        items = []
        for position, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            match = self.LINE.match(line)
            if match is None:
                errors.append("%s line %d skipped: expected 'A: text' or 'B: text'" % (short_name, position))
            else:
                items.append((position, match.group("speaker"), match.group("time") or "", match.group("text")))
        return setup, items


class MeetingFileReader:
    """Lists and reads meeting files from a folder."""

    def __init__(self, folder: str, parsers: Optional[Dict[str, MeetingFileParser]] = None):
        self._folder = folder
        self._parsers = parsers or {".json": JsonMeetingParser(), ".txt": TextMeetingParser()}

    @property
    def folder(self) -> str:
        return self._folder

    def list_files(self) -> List[str]:
        """Names of supported files in the folder (sorted). A missing folder means none."""
        try:
            names = os.listdir(self._folder)
        except OSError:
            return []
        return sorted(n for n in names if os.path.splitext(n)[1].lower() in self._parsers)

    def read(self, name: str, setup: MeetingSetup) -> ParseResult:
        """Read one file by name (from the folder) or by path. Never raises."""
        path = name if os.path.isabs(name) or os.path.exists(name) else os.path.join(self._folder, name)
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                content = handle.read()
        except (OSError, UnicodeDecodeError) as error:
            return ParseResult(errors=["cannot read %s: %s" % (path, error)])
        return self.parse_content(path, content, setup)

    def parse_content(self, name: str, content: str, setup: MeetingSetup) -> ParseResult:
        """Parse text that is already in memory (e.g. a file uploaded in the GUI). Never raises."""
        parser = self._parsers.get(os.path.splitext(name)[1].lower())
        if parser is None:
            return ParseResult(errors=["unsupported file type: %s" % name])
        return parser.parse(name, content, setup)

    def parse_bytes(self, name: str, data: bytes, setup: MeetingSetup) -> ParseResult:
        """Like parse_content for raw uploaded bytes; undecodable bytes become an error, not a crash."""
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            return ParseResult(errors=["cannot read %s: %s" % (name, error)])
        return self.parse_content(name, content, setup)

