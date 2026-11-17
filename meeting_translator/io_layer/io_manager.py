"""IOManager: collects and validates user input; displays records, lists, results and summaries.
No domain logic lives here."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from ..data_layer.query import RecordQuery
from ..exceptions import SpeechError, ValidationError
from ..models import (DETECTED_LANGUAGES, MAX_SENTENCE_CHARS, Language, MeetingSetup, Outcome, Party,
                      ProcessedRecord, TextCleaner, Tone, Utterance)
from ..pipeline import PipelineObserver
from ..reports import MeetingReport
from .console import Console
from .formatters import Exporter, RecordFormatter
from .meeting_files import MeetingFileReader
from .speech import AUDIO_EXTENSIONS, MAX_AUDIO_BYTES, SpeechTranscriber


class IOManager:
    """The user boundary. Collaborates with a Console (terminal), a MeetingFileReader (input
    files), a RecordFormatter (presentation) and an optional SpeechTranscriber (voice input) that
    are handed in (aggregation)."""

    MENU_CHOICES = [str(n) for n in range(1, 11)]

    def __init__(self, console: Console, reader: MeetingFileReader, formatter: Optional[RecordFormatter] = None,
                 report_dir: str = os.path.join("data", "reports"), transcriber: Optional[SpeechTranscriber] = None):
        self._console = console
        self._reader = reader
        self._formatter = formatter or RecordFormatter()
        self._report = MeetingReport()
        self._report_dir = report_dir
        self._transcriber = transcriber

    # ----- plain output -----
    def show_message(self, text: str) -> None:
        self._console.show(text)

    def show_error(self, text: str) -> None:
        self._console.show_error(text)

    # ----- menus and prompts -----
    def prompt_menu(self, setup: MeetingSetup, context_count: int) -> Optional[str]:
        self.show_message(
            "\n=== Meeting Translator ===\n"
            "Meeting: %s\n"
            "  A: %s    B: %s\n"
            "1. Say a sentence (type it)\n"
            "2. Process meeting files from the input folder\n"
            "3. Show the latest sentence and the previous %d\n"
            "4. View the full transcript\n"
            "5. Filter records\n"
            "6. Summary\n"
            "7. Meeting report (also saved to a file)\n"
            "8. Meeting setup (names and languages)\n"
            "9. Quit\n"
            "10. Say a sentence from a voice recording (audio file, speech-to-text)"
            % (setup.meeting, setup.party("A").describe(), setup.party("B").describe(), context_count))
        return self._console.ask_choice("Choose 1-10: ", self.MENU_CHOICES)

    def prompt_speaker(self, setup: MeetingSetup) -> Optional[str]:
        """'A' or 'B', or None if input ended."""
        self.show_message("Who is speaking?  1) %s   2) %s" % (setup.party("A").describe(), setup.party("B").describe()))
        choice = self._console.ask_choice("Speaker 1-2: ", ["1", "2"])
        return None if choice is None else MeetingSetup.PARTY_IDS[int(choice) - 1]

    def prompt_voice_speaker(self, setup: MeetingSetup) -> Optional[str]:
        """'A', 'B', or 'AUTO' (detect from spoken language), or None if input ended."""
        self.show_message("Who is speaking?  1) %s   2) %s   3) Auto-detect from voice"
                          % (setup.party("A").describe(), setup.party("B").describe()))
        choice = self._console.ask_choice("Speaker 1-3: ", ["1", "2", "3"])
        if choice is None:
            return None
        return "AUTO" if choice == "3" else MeetingSetup.PARTY_IDS[int(choice) - 1]

    def prompt_sentence(self) -> Optional[str]:
        """One typed sentence, or None if input ended."""
        while True:
            text = self._console.ask("Sentence: ")
            if text is None:
                return None
            if not text:
                self.show_error("the sentence cannot be empty")
            elif len(text) > MAX_SENTENCE_CHARS:
                self.show_error("the sentence is too long (max %d characters)" % MAX_SENTENCE_CHARS)
            else:
                return text

    def build_utterance(self, setup: MeetingSetup, speaker_id: str, text: str,
                        input_type: str = "text") -> Optional[Utterance]:
        """A validated utterance, or None after showing why it is invalid."""
        try:
            return Utterance.create(setup, speaker_id, text, input_type=input_type)
        except ValidationError as error:
            self.show_error(str(error))
            return None

    # ----- voice input (speech-to-text) -----
    def prompt_audio_path(self) -> Optional[str]:
        """The path of a recording, or None if the user pressed Enter or input ended."""
        path = self._console.ask("Audio file (%s) - press Enter to cancel: " % ", ".join(AUDIO_EXTENSIONS[:4] + ("...",)))
        if not path:
            return None
        return path.strip("\"'")  # a file dragged into the terminal arrives wrapped in quotes

    def _read_audio(self, path: str) -> Optional[bytes]:
        """The bytes of an audio file, or None after showing why it cannot be used."""
        if not os.path.isfile(path):
            self.show_error("audio file not found: %s" % path)
            return None
        if not path.lower().endswith(AUDIO_EXTENSIONS):
            self.show_error("that does not look like an audio file (use one of: %s)" % ", ".join(AUDIO_EXTENSIONS))
            return None
        try:
            if os.path.getsize(path) > MAX_AUDIO_BYTES:
                self.show_error("that recording is larger than %d MB; use a shorter one" % (MAX_AUDIO_BYTES // (1024 * 1024)))
                return None
            with open(path, "rb") as handle:
                return handle.read()
        except OSError as error:
            self.show_error("could not read %s: %s" % (path, error))
            return None

    def _run_transcription(self, path: str, language: Optional[Language],
                           allowed_languages=None):
        """Read and transcribe an audio file, or return None after showing why it failed."""
        if self._transcriber is None:
            self.show_error("speech-to-text is not available in this setup")
            return None
        audio = self._read_audio(path)
        if audio is None:
            return None
        try:
            result = self._transcriber.transcribe(audio, language, allowed_languages=allowed_languages)
        except SpeechError as error:
            self.show_error(str(error))
            return None
        if result.is_empty:
            self.show_error("no speech was detected in that recording")
            return None
        return result

    def transcribe_audio_file(self, setup: MeetingSetup, speaker_id: str, path: str) -> Optional[str]:
        """Speech-to-text for one recording, in the language the speaker is set to speak.
        The text, or None after showing why it could not be done."""
        result = self._run_transcription(path, setup.party(speaker_id).language)
        return None if result is None else result.text

    def transcribe_audio_with_detection(self, setup: MeetingSetup, path: str,
                                        speaker_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """Transcribe an audio file, optionally auto-detecting the speaker from the spoken language.
        Returns (text, resolved_speaker_id), or None on failure/cancellation."""
        hint = None if speaker_id is None else setup.party(speaker_id).language
        allowed = (setup.party("A").language, setup.party("B").language) if speaker_id is None else None
        result = self._run_transcription(path, hint, allowed_languages=allowed)
        if result is None:
            return None
        if speaker_id is not None:
            return result.text, speaker_id
        detected = setup.party_for_language(result.language)
        if detected is not None:
            self.show_message("Detected %s -> %s: %s"
                              % (result.language.value, detected, setup.party(detected).describe()))
            return result.text, detected
        reason = ("Could not match spoken language to English/Indonesian/Chinese."
                  if result.language is None
                  else "Detected %s, which does not uniquely match one party." % result.language.value)
        self.show_message(reason)
        chosen = self.prompt_speaker(setup)
        return None if chosen is None else (result.text, chosen)

    def confirm_transcript(self, text: str) -> Optional[str]:
        """Show what was heard. Enter accepts it, a typed sentence replaces it (speech recognition can
        mishear names and numbers), /cancel drops it. The final text, or None."""
        self.show_message('Heard: "%s"' % text)
        answer = self._console.ask("Press Enter to translate it, type a corrected sentence, or /cancel: ")
        if answer is None or answer.lower() == "/cancel":
            return None
        return answer or text

    def _prompt_language_or_keep(self, label: str, current: Language) -> Optional[Language]:
        self.show_message("%s: 1) English  2) Indonesian  3) Chinese  (Enter keeps %s)" % (label, current.value))
        choice = self._console.ask_choice("Choice: ", ["", "1", "2", "3"])
        if choice is None:
            return None
        return current if choice == "" else list(Language)[int(choice) - 1]

    def prompt_setup(self, current: MeetingSetup) -> Optional[MeetingSetup]:
        """Meeting name, party names and languages (Enter keeps the current value).
        None if input ended."""
        meeting = self._console.ask("Meeting name [%s]: " % current.meeting)
        if meeting is None:
            return None
        parties = {}
        for party_id in MeetingSetup.PARTY_IDS:
            party = current.party(party_id)
            name = self._console.ask("Name of party %s [%s]: " % (party_id, party.name))
            language = self._prompt_language_or_keep("Language of party %s" % party_id, party.language)
            if name is None or language is None:
                return None
            parties[party_id] = Party(TextCleaner.label(name, party.name, 40), language)
        return MeetingSetup(TextCleaner.label(meeting, current.meeting, 60), parties["A"], parties["B"])

    def prompt_filter(self, setup: MeetingSetup) -> Optional[RecordQuery]:
        """How to filter the records, or None."""
        self.show_message("Filter by: 1) tone  2) language spoken  3) translated into  4) speaker  5) outcome")
        choice = self._console.ask_choice("Filter 1-5: ", ["1", "2", "3", "4", "5"])
        if choice is None:
            return None
        if choice == "4":
            self.show_message("1) %s   2) %s" % (setup.party("A").describe(), setup.party("B").describe()))
            value = self._console.ask_choice("Speaker 1-2: ", ["1", "2"])
            return None if value is None else RecordQuery(speakers=[setup.party(MeetingSetup.PARTY_IDS[int(value) - 1]).name])
        options = {"1": ("Tone", Tone.values(), "tones"), "2": ("Language", DETECTED_LANGUAGES, "languages"),
                   "3": ("Language", Language.values(), "target_languages"),
                   "5": ("Outcome", [o.value for o in Outcome], "outcome")}
        label, valid, keyword = options[choice]
        value = self._console.ask_choice("%s (%s): " % (label, "/".join(valid)), valid)
        if value is None:
            return None
        return RecordQuery(outcome=value) if keyword == "outcome" else RecordQuery(**{keyword: [value]})

    def prompt_file_choice(self) -> Optional[List[str]]:
        """Let the user pick one input file (or all). A list of file names, or None."""
        files = self._reader.list_files()
        if not files:
            self.show_error("no .json or .txt files found in the '%s' folder" % self._reader.folder)
            return None
        self.show_message("\nFiles in '%s':" % self._reader.folder)
        for number, name in enumerate(files, start=1):
            self.show_message("  %d. %s" % (number, name))
        self.show_message("  A. all files")
        choice = self._console.ask_choice("Choose a file: ", [str(n) for n in range(1, len(files) + 1)] + ["A", "a"])
        if choice is None:
            return None
        return files if choice.lower() == "a" else [files[int(choice) - 1]]

    # ----- input files -----
    def list_input_files(self) -> List[str]:
        return self._reader.list_files()

    def read_utterances(self, file_names: List[str], setup: MeetingSetup, name_meeting_after_file: bool = False) -> List[Utterance]:
        """Read the chosen files; a de-duplicated list. With name_meeting_after_file, a file that
        does not name its own meeting becomes a meeting called after the file (repeatable batch runs)."""
        utterances, seen = [], set()
        for name in file_names:
            file_setup = setup
            if name_meeting_after_file:
                stem = TextCleaner.label(os.path.splitext(name)[0], setup.meeting, 60)
                file_setup = MeetingSetup(stem, setup.party("A"), setup.party("B"))
            result = self._reader.read(name, file_setup)
            for message in result.errors:
                self.show_error(message)
            for utterance in result.utterances:
                if utterance.id not in seen:
                    seen.add(utterance.id)
                    utterances.append(utterance)
        return utterances

    # ----- displaying results -----
    def show_sentence(self, record: ProcessedRecord) -> None:
        self.show_message(self._formatter.sentence(record))

    def show_conversation(self, latest: Optional[ProcessedRecord], previous: List[ProcessedRecord]) -> None:
        self.show_message(self._formatter.conversation(latest, previous))

    def show_transcript(self, records: List[ProcessedRecord]) -> None:
        self.show_message(self._formatter.transcript(records))

    def show_summary(self, records: List[ProcessedRecord]) -> None:
        self.show_message(self._formatter.summary(records))

    def show_counts(self, counts: dict) -> None:
        self.show_message("\nDone: %(processed)d translated, %(skipped)d already done, %(failed)d failed." % counts)

    # ----- new feature: reports -----
    def show_report(self, meeting: str, records: List[ProcessedRecord]) -> str:
        """Display the meeting report and save it as a text file. Returns the report text."""
        text = self._report.render(records, "Meeting report: " + meeting)
        self.show_message(text)
        if records:
            self.save_text(os.path.join(self._report_dir, self._formatter.safe_filename(meeting) + "-report.txt"), text)
        return text

    def export(self, records: List[ProcessedRecord], exporter: Exporter, path: str) -> bool:
        """Write the records with any Exporter (CSV, JSON, text...). True on success."""
        return self.save_text(path, exporter.export(records))

    def save_text(self, path: str, text: str) -> bool:
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError as error:
            self.show_error("could not write %s: %s" % (path, error))
            return False
        self.show_message("Saved %s" % path)
        return True


class ConsoleObserver(PipelineObserver):
    """Shows each pipeline result as it happens (Observer pattern; the pipeline stays print-free)."""

    def __init__(self, io: IOManager):
        self._io = io

    def on_processed(self, record: ProcessedRecord) -> None:
        self._io.show_sentence(record)

    def on_failed(self, utterance: Utterance) -> None:
        self._io.show_error("AI translation failed for a sentence from %s (see the log); continuing"
                            % utterance.speaker.name)
