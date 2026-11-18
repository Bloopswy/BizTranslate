import json
import os
import unittest
from unittest import mock

from meeting_translator.exceptions import TranscriptionError
from meeting_translator.io_layer import (Console, CsvExporter, Exporter, IOManager, JsonExporter, JsonMeetingParser,
                                         MeetingFileParser, MeetingFileReader, RecordFormatter, TextExporter,
                                         TextMeetingParser, Transcription)
from meeting_translator.data_layer import RecordQuery
from meeting_translator.models import Language, Outcome
from tests.fake_console import ScriptedConsole
from tests.fake_speech import FakeTranscriber
from tests.helpers import TempDir, make_setup, saved


def make_io(*answers, folder="input", report_dir="reports", transcriber=None):
    console = ScriptedConsole(*answers)
    return IOManager(console, MeetingFileReader(folder), RecordFormatter("UTC"), report_dir, transcriber), console


class ConsoleTests(unittest.TestCase):
    def test_reprompts_until_valid_and_eof_gives_none(self):
        console = ScriptedConsole("x", "9", " 2 ")
        self.assertEqual(console.ask_choice("?", ["1", "2"]), "2")
        self.assertEqual(sum("please enter" in line for line in console.shown), 2)
        self.assertIsNone(console.ask_choice("?", ["1"]))  # end of input


class IOManagerPromptTests(unittest.TestCase):
    def test_menu_speaker_and_sentence(self):
        io, console = make_io("0", "5", "2", "", "   ", "x" * 2001, "Hello there")
        self.assertEqual(io.prompt_menu(make_setup(), 3), "5")
        self.assertEqual(io.prompt_speaker(make_setup()), "B")
        self.assertEqual(io.prompt_sentence(), "Hello there")
        self.assertTrue(any("cannot be empty" in s for s in console.shown))
        self.assertTrue(any("too long" in s for s in console.shown))

    def test_build_utterance_reports_validation_errors(self):
        io, console = make_io()
        self.assertIsNone(io.build_utterance(make_setup(), "Z", "hi"))
        self.assertIn("speaker must be A or B", console.shown[-1])
        self.assertIsNotNone(io.build_utterance(make_setup(), "A", "hi"))

    def test_setup_prompt_keeps_current_on_enter_and_changes_values(self):
        io, _ = make_io("standup", "", "", "Beta Co", "3")
        new = io.prompt_setup(make_setup("old"))
        self.assertEqual(new.meeting, "standup")
        self.assertEqual(new.party("A").name, "Acme")
        self.assertEqual((new.party("B").name, new.party("B").language.value), ("Beta Co", "Chinese"))
        self.assertIsNone(make_io("only meeting")[0].prompt_setup(make_setup()))  # input ended midway

    def test_filter_prompt_builds_queries(self):
        self.assertEqual(make_io("1", "angry")[0].prompt_filter(make_setup()), RecordQuery(tones=["angry"]))
        self.assertEqual(make_io("4", "2")[0].prompt_filter(make_setup()), RecordQuery(speakers=["Mitra"]))
        self.assertEqual(make_io("5", "CHECK")[0].prompt_filter(make_setup()), RecordQuery(outcome="CHECK"))
        self.assertEqual(make_io("3", "Chinese")[0].prompt_filter(make_setup()), RecordQuery(target_languages=["Chinese"]))
        self.assertIsNone(make_io()[0].prompt_filter(make_setup()))


class FileParserTests(unittest.TestCase):
    def test_json_object_sets_parties_and_utterances(self):
        content = json.dumps({"meeting": "demo", "parties": {"A": {"name": "N", "language": "English"},
                                                              "B": {"name": "H", "language": "Chinese"}},
                              "utterances": [{"speaker": "A", "transcript": "Hi", "timestamp": "2026-10-14T14:00:03+08:00"},
                                             {"speaker": "B", "transcript": "你好"}]})
        result = JsonMeetingParser().parse("demo.json", content, make_setup())
        self.assertEqual([u.meeting for u in result.utterances], ["demo", "demo"])
        self.assertEqual(result.utterances[1].listener.name, "N")
        self.assertEqual(result.errors, [])

    def test_json_bad_inputs_never_raise(self):
        parser = JsonMeetingParser()
        self.assertIn("not valid JSON", parser.parse("a.json", "{oops", make_setup()).errors[0])
        self.assertIn("list of utterances", parser.parse("a.json", '{"x": 1}', make_setup()).errors[0])
        result = parser.parse("a.json", json.dumps([5, {"speaker": "Q", "transcript": "x"}, {"speaker": "A", "transcript": ""},
                                                    {"speaker": "A", "transcript": "ok"}]), make_setup())
        self.assertEqual(len(result.utterances), 1)
        self.assertEqual(len(result.errors), 3)

    def test_text_lines(self):
        content = "[2026-10-14T09:00:05+08:00] A: Hello\nB：你好\n\nthis line is wrong\nb: lowercase speaker"
        result = TextMeetingParser().parse("x.txt", content, make_setup())
        self.assertEqual([u.speaker_id for u in result.utterances], ["A", "B", "B"])
        self.assertEqual(result.utterances[0].timestamp, "2026-10-14T09:00:05+08:00")
        self.assertEqual(len(result.errors), 1)

    def test_parsers_share_a_base_type(self):
        self.assertTrue(all(isinstance(p, MeetingFileParser) for p in (JsonMeetingParser(), TextMeetingParser())))


class FileReaderTests(unittest.TestCase):
    def test_list_read_and_failures(self):
        with TempDir() as folder:
            for name, text in (("b.txt", "A: hi"), ("a.json", "[]"), ("skip.csv", "x")):
                with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                    handle.write(text)
            reader = MeetingFileReader(folder)
            self.assertEqual(reader.list_files(), ["a.json", "b.txt"])
            self.assertEqual(len(reader.read("b.txt", make_setup()).utterances), 1)
            self.assertIn("cannot read", reader.read("missing.txt", make_setup()).errors[0])
            self.assertIn("unsupported", reader.read("skip.csv", make_setup()).errors[0])
            with open(os.path.join(folder, "bad.txt"), "wb") as handle:
                handle.write(b"\xff\xfe\x00bad")
            self.assertTrue(reader.read("bad.txt", make_setup()).errors)

    def test_parse_uploaded_bytes(self):
        reader = MeetingFileReader("none")
        result = reader.parse_bytes("up.txt", "A: hello\nB: 你好".encode("utf-8"), make_setup())
        self.assertEqual(len(result.utterances), 2)
        self.assertIn("cannot read", reader.parse_bytes("bad.txt", b"\xff\xfe\x00", make_setup()).errors[0])
        self.assertIn("unsupported", reader.parse_bytes("x.pdf", b"x", make_setup()).errors[0])

    def test_missing_folder_lists_nothing(self):
        self.assertEqual(MeetingFileReader("no/such/folder").list_files(), [])

    def test_read_utterances_dedupes_and_names_meeting_after_file(self):
        with TempDir() as folder:
            with open(os.path.join(folder, "standup.txt"), "w") as handle:
                handle.write("A: hi\nA: hi")
            io, _ = make_io(folder=folder)
            same = io.read_utterances(["standup.txt", "standup.txt"], make_setup(), name_meeting_after_file=True)
            self.assertEqual(len(same), 2)  # two lines are two sentences; the repeated file adds nothing
            self.assertEqual({u.meeting for u in same}, {"standup"})
            self.assertEqual({u.meeting for u in io.read_utterances(["standup.txt"], make_setup())}, {"m1"})

    def test_prompt_file_choice(self):
        with TempDir() as folder:
            for name in ("a.txt", "b.txt"):
                open(os.path.join(folder, name), "w").close()
            self.assertEqual(make_io("2", folder=folder)[0].prompt_file_choice(), ["b.txt"])
            self.assertEqual(make_io("A", folder=folder)[0].prompt_file_choice(), ["a.txt", "b.txt"])
        io, console = make_io(folder="nowhere")
        self.assertIsNone(io.prompt_file_choice())
        self.assertIn("no .json or .txt", console.shown[-1])


class FormatterTests(unittest.TestCase):
    def test_views(self):
        f = RecordFormatter("UTC")
        records = [saved(1, "Good morning"), saved(2, "Next")]
        self.assertIn("Selamat pagi", f.sentence(records[0]))
        self.assertIn("09:02:00", f.short_sentence(records[1]))
        self.assertEqual(f.conversation(None, []), "Nothing has been said in this meeting yet.")
        self.assertIn("Previous 1 sentences", f.conversation(records[1], records[:1]))
        self.assertIn("no earlier sentences", f.conversation(records[0], []))
        self.assertEqual(f.transcript([]), "No sentences.")
        self.assertEqual(f.summary([]), "No records yet.")
        self.assertIn("ACCEPT=2", f.summary(records))
        self.assertEqual(f.safe_filename("a b/c"), "a_b_c")
        self.assertEqual(f.safe_filename("///"), "meeting")


class ExporterTests(unittest.TestCase):
    def test_polymorphic_exporters(self):
        records = [saved(1, "a, with comma"), saved(2, "b")]
        for exporter in (CsvExporter(), JsonExporter(), TextExporter("UTC")):
            self.assertIsInstance(exporter, Exporter)
            text = exporter.export(records)
            self.assertIn("a, with comma" if not isinstance(exporter, CsvExporter) else '"a, with comma"', text)
        self.assertEqual(len(json.loads(JsonExporter().export(records))), 2)
        self.assertEqual(TextExporter().export([]), "")

    def test_export_to_disk_and_failure(self):
        with TempDir() as folder:
            io, console = make_io()
            path = os.path.join(folder, "sub", "out.csv")
            self.assertTrue(io.export([saved(1)], CsvExporter(), path))
            self.assertTrue(os.path.exists(path))
            blocker = os.path.join(folder, "file")
            open(blocker, "w").close()
            self.assertFalse(io.export([saved(1)], CsvExporter(), os.path.join(blocker, "x.csv")))
            self.assertIn("could not write", console.shown[-1])


class IOManagerReportTests(unittest.TestCase):
    def test_report_is_shown_and_saved(self):
        with TempDir() as folder:
            io, console = make_io(report_dir=folder)
            text = io.show_report("my meeting", [saved(1, outcome=Outcome.TENSION, score=80)])
            self.assertIn("Meeting report: my meeting", text)
            self.assertTrue(os.path.exists(os.path.join(folder, "my_meeting-report.txt")))
            io.show_report("empty", [])
            self.assertFalse(os.path.exists(os.path.join(folder, "empty-report.txt")))


class IOManagerSpeechTests(unittest.TestCase):
    @staticmethod
    def make_audio(folder, name="talk.wav", data=b"RIFFfake-audio"):
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_menu_offers_voice_input_as_option_10(self):
        io, console = make_io("10")
        self.assertEqual(io.prompt_menu(make_setup(), 3), "10")
        self.assertTrue(any("10. Say a sentence from a voice recording" in line for line in console.shown))
        self.assertTrue(any("9. Quit" in line for line in console.shown), "the existing numbers did not change")

    def test_audio_file_is_transcribed_in_the_speakers_language(self):
        with TempDir() as folder:
            path = self.make_audio(folder)
            transcriber = FakeTranscriber(Transcription("Selamat pagi", Language.INDONESIAN))
            io, _ = make_io(transcriber=transcriber)
            self.assertEqual(io.transcribe_audio_file(make_setup(), "B", path), "Selamat pagi")
            self.assertEqual(transcriber.calls, [(b"RIFFfake-audio", Language.INDONESIAN)])
            io.transcribe_audio_file(make_setup(), "A", path)
            self.assertEqual(transcriber.calls[-1][1], Language.ENGLISH)

    def test_unusable_files_are_explained(self):
        with TempDir() as folder:
            good = self.make_audio(folder)
            notes = self.make_audio(folder, "notes.txt")
            transcriber = FakeTranscriber()
            io, console = make_io(transcriber=transcriber)
            self.assertIsNone(io.transcribe_audio_file(make_setup(), "A", os.path.join(folder, "missing.wav")))
            self.assertIn("not found", console.shown[-1])
            self.assertIsNone(io.transcribe_audio_file(make_setup(), "A", notes))
            self.assertIn("does not look like an audio file", console.shown[-1])
            with mock.patch("meeting_translator.io_layer.io_manager.MAX_AUDIO_BYTES", 5):
                self.assertIsNone(io.transcribe_audio_file(make_setup(), "A", good))
            self.assertIn("larger than", console.shown[-1])
            self.assertEqual(transcriber.calls, [], "nothing unusable ever reaches the transcriber")

    def test_speech_problems_are_shown_not_raised(self):
        with TempDir() as folder:
            path = self.make_audio(folder)
            io, console = make_io(transcriber=FakeTranscriber(TranscriptionError("Could not transcribe (bad audio).")))
            self.assertIsNone(io.transcribe_audio_file(make_setup(), "A", path))
            self.assertIn("bad audio", console.shown[-1])
            io, console = make_io(transcriber=FakeTranscriber(Transcription("   ")))
            self.assertIsNone(io.transcribe_audio_file(make_setup(), "A", path))
            self.assertIn("no speech was detected", console.shown[-1])
            io, console = make_io()  # no transcriber configured
            self.assertIsNone(io.transcribe_audio_file(make_setup(), "A", path))
            self.assertIn("not available", console.shown[-1])

    def test_confirm_transcript_accepts_corrects_or_cancels(self):
        io, console = make_io("", "Fixed sentence", "/cancel", "/CANCEL")
        self.assertEqual(io.confirm_transcript("Heard text"), "Heard text")
        self.assertEqual(io.confirm_transcript("Heard text"), "Fixed sentence")
        self.assertIsNone(io.confirm_transcript("x"))
        self.assertIsNone(io.confirm_transcript("x"))
        self.assertIsNone(io.confirm_transcript("x"))  # end of input
        self.assertTrue(any('Heard: "Heard text"' in line for line in console.shown))

    def test_prompt_audio_path_strips_quotes_and_cancels(self):
        io, _ = make_io('"C:\\Users\\me\\talk.wav"', "'/tmp/a.mp3'", "")
        self.assertEqual(io.prompt_audio_path(), "C:\\Users\\me\\talk.wav")
        self.assertEqual(io.prompt_audio_path(), "/tmp/a.mp3")
        self.assertIsNone(io.prompt_audio_path())  # Enter = cancel
        self.assertIsNone(io.prompt_audio_path())  # end of input

    def test_voice_utterances_remember_how_they_were_entered(self):
        io, _ = make_io()
        self.assertEqual(io.build_utterance(make_setup(), "A", "hi", "voice").input_type, "voice")
        self.assertEqual(io.build_utterance(make_setup(), "A", "hi").input_type, "text")


if __name__ == "__main__":
    unittest.main()
