"""Application: builds the object graph (composition root) and runs the terminal app.

Usage:
    python main.py                 interactive menu
    python main.py --batch         translate every meeting file in the input folder, then exit
    python main.py --meeting standup --a-name Acme --a-language English --b-name Mitra --b-language Indonesian
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import List, Optional

from .ai_layer import AIManager, GeminiClient
from .config import RuleSettings, Settings
from .data_layer import DataManager, RepositoryFactory
from .io_layer import (Console, ConsoleObserver, IOManager, MeetingFileReader, RecordFormatter, SpeechTranscriber,
                       WhisperTranscriber)
from .logic_layer import LogicManager
from .models import Language, MeetingSetup, Party
from .pipeline import MeetingPipeline


class Application:
    """Wires the four managers together and drives them from the terminal."""

    def __init__(self, settings: Settings, io: IOManager, data: DataManager, logic: LogicManager,
                 pipeline: MeetingPipeline):
        self._settings = settings
        self._io = io
        self._data = data
        self._logic = logic
        self._pipeline = pipeline

    @classmethod
    def build(cls, settings: Settings, console: Optional[Console] = None, ai_client=None,
              transcriber: Optional[SpeechTranscriber] = None) -> "Application":
        """Create every manager. `ai_client` and `transcriber` let tests plug in fakes instead of the
        live API and the Whisper model."""
        client = ai_client or GeminiClient(settings.api_key, settings.model)
        data = DataManager(RepositoryFactory.for_path(settings.data_path))
        logic = LogicManager(RuleSettings.load(settings.rules_path))
        io = IOManager(console or Console(), MeetingFileReader(settings.input_dir), RecordFormatter(),
                       settings.report_dir, transcriber or WhisperTranscriber(settings.whisper_model))
        pipeline = MeetingPipeline(AIManager(client), logic, data, [ConsoleObserver(io)])
        return cls(settings, io, data, logic, pipeline)

    @staticmethod
    def setup_logging(path: str) -> None:
        """Log to a file only, so all terminal output stays in the IOManager."""
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        logging.basicConfig(filename=path, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # ----- batch mode -----
    def run_batch(self, setup: MeetingSetup, name_meeting_after_file: bool = True) -> None:
        files = self._io.list_input_files()
        if not files:
            self._io.show_error("no .json or .txt files found in the input folder")
            return
        utterances = self._io.read_utterances(files, setup, name_meeting_after_file)
        self._io.show_counts(self._pipeline.process_many(utterances))
        for meeting in dict.fromkeys(u.meeting for u in utterances):  # unique, in order
            self._io.show_message("\n=== Meeting: %s ===" % meeting)
            self._show_latest(meeting)
        self._io.show_summary(self._data.all())

    # ----- interactive mode -----
    def _show_latest(self, meeting: str) -> None:
        latest, previous = self._data.latest_with_context(meeting, self._logic.settings.context_sentences)
        self._io.show_conversation(latest, previous)

    def _translate_one(self, setup: MeetingSetup, utterance) -> None:
        """Run one validated utterance (or nothing, if the user cancelled) through the pipeline."""
        if utterance is not None:
            self._io.show_counts(self._pipeline.process_many([utterance]))
            self._show_latest(setup.meeting)

    def _utterance_from_voice(self, setup: MeetingSetup):
        """Menu 10: pick the speaker (or auto-detect from voice) and an audio file, transcribe it,
        let the user fix the text. The utterance, or None if anything was cancelled or failed."""
        speaker = self._io.prompt_voice_speaker(setup)
        path = self._io.prompt_audio_path() if speaker else None
        if not path:
            return None
        transcribed = self._io.transcribe_audio_with_detection(setup, path, None if speaker == "AUTO" else speaker)
        if transcribed is None:
            return None
        text, resolved_speaker = transcribed
        text = self._io.confirm_transcript(text)
        return self._io.build_utterance(setup, resolved_speaker, text, "voice") if text else None

    def run_interactive(self, setup: MeetingSetup) -> None:
        while True:
            choice = self._io.prompt_menu(setup, self._logic.settings.context_sentences)
            if choice is None or choice == "9":
                self._io.show_message("Goodbye.")
                return
            setup = self._handle_choice(choice, setup)

    def _handle_choice(self, choice: str, setup: MeetingSetup) -> MeetingSetup:
        if choice == "1":
            speaker = self._io.prompt_speaker(setup)
            text = self._io.prompt_sentence() if speaker else None
            self._translate_one(setup, self._io.build_utterance(setup, speaker, text) if text else None)
        elif choice == "10":
            self._translate_one(setup, self._utterance_from_voice(setup))
        elif choice == "2":
            chosen = self._io.prompt_file_choice()
            if chosen:
                self._io.show_counts(self._pipeline.process_many(self._io.read_utterances(chosen, setup)))
        elif choice == "3":
            self._show_latest(setup.meeting)
        elif choice == "4":
            self._io.show_transcript(self._data.meeting_records(setup.meeting))
        elif choice == "5":
            query = self._io.prompt_filter(setup)
            if query is not None:
                self._io.show_transcript(self._data.query(query))
        elif choice == "6":
            self._io.show_summary(self._data.all())
        elif choice == "7":
            self._io.show_report(setup.meeting, self._data.meeting_records(setup.meeting))
        elif choice == "8":
            return self._io.prompt_setup(setup) or setup
        return setup

    # ----- entry point -----
    @classmethod
    def main(cls, argv: Optional[List[str]] = None, env_file: str = ".env") -> int:
        parser = argparse.ArgumentParser(description="Meeting translator for two parties (English / Indonesian / Chinese)")
        parser.add_argument("--batch", action="store_true", help="translate the meeting files in the input folder and exit")
        parser.add_argument("--meeting", help="meeting name (default: today's date, or the file name in --batch)")
        parser.add_argument("--a-name", help="name of party A")
        parser.add_argument("--a-language", choices=Language.values(), help="language of party A (default English)")
        parser.add_argument("--b-name", help="name of party B")
        parser.add_argument("--b-language", choices=Language.values(), help="language of party B (default Indonesian)")
        args = parser.parse_args(argv)

        settings = Settings.from_environment(env_file)
        cls.setup_logging(settings.log_path)
        console = Console()
        if not settings.api_key:
            console.show_error(
                "GEMINI_API_KEY is not set. Either create a file named .env in this folder containing\n"
                "  GEMINI_API_KEY=your-key\n"
                "or set it in your terminal first (macOS/Linux: export GEMINI_API_KEY=your-key, "
                "Windows PowerShell: $env:GEMINI_API_KEY=\"your-key\").")
            return 1

        app = cls.build(settings, console)
        default = MeetingSetup.default()
        setup = MeetingSetup.from_dict({
            "meeting": args.meeting,
            "parties": {"A": {"name": args.a_name, "language": args.a_language},
                        "B": {"name": args.b_name, "language": args.b_language}},
        }, default)
        loaded = app._data.load()
        console.show("Loaded %d saved sentence(s). Model: %s" % (loaded, settings.model))
        if args.batch:
            # an explicit --meeting name applies to every file; otherwise each file is its own meeting
            app.run_batch(setup, name_meeting_after_file=not args.meeting)
        else:
            app.run_interactive(setup)
        return 0
