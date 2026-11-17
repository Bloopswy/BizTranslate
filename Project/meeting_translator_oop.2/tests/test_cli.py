import json
import os
import sys
import unittest
from unittest import mock

from meeting_translator.ai_layer import AIManager
from meeting_translator.cli import Application
from meeting_translator.config import Settings
from meeting_translator.io_layer import Transcription, WhisperTranscriber
from meeting_translator.models import Language
from tests.fake_ai import FailingClient, ScriptedClient
from tests.fake_console import ScriptedConsole
from tests.fake_speech import FakeTranscriber
from tests.helpers import TempDir, make_setup


class ApplicationTests(unittest.TestCase):
    def build(self, folder, client, *answers, transcriber=None):
        env = {"GEMINI_API_KEY": "k", "DATA_FILE": os.path.join(folder, "records.json"),
               "LOG_FILE": os.path.join(folder, "app.log"), "INPUT_DIR": os.path.join(folder, "input"),
               "REPORT_DIR": os.path.join(folder, "reports"), "RULES_FILE": os.path.join(folder, "none.json")}
        console = ScriptedConsole(*answers)
        return Application.build(Settings(env), console, client, transcriber), console

    def test_interactive_session_end_to_end(self):
        with TempDir() as folder:
            client = ScriptedClient(ScriptedClient.json_reply(tone="angry", intensity=5, tone_confidence=0.9))
            # 1 say a sentence (speaker 1), 4 transcript, 6 summary, 7 report, 9 quit
            app, console = self.build(folder, client, "1", "1", "We need this fixed now", "4", "6", "7", "9")
            app.run_interactive(make_setup("live"))
            output = "\n".join(console.shown)
            self.assertIn("1 translated, 0 already done, 0 failed", output)
            self.assertIn("TENSION", output)
            self.assertIn("Total sentences: 1", output)
            self.assertIn("Meeting report: live", output)
            self.assertIn("Goodbye.", output)
            self.assertTrue(os.path.exists(os.path.join(folder, "records.json")))
            self.assertTrue(os.path.exists(os.path.join(folder, "reports", "live-report.txt")))

    @staticmethod
    def audio_file(folder, name="talk.wav"):
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(b"fake-audio")
        return path

    def test_voice_option_transcribes_an_audio_file_and_translates_it(self):
        with TempDir() as folder:
            audio = self.audio_file(folder)
            transcriber = FakeTranscriber(Transcription("Selamat pagi semuanya", Language.INDONESIAN))
            client = ScriptedClient(ScriptedClient.json_reply(translation="Good morning everyone",
                                                              detected_language="Indonesian"))
            # 10 voice, speaker 2 (B, Indonesian), the file, Enter = accept what was heard, 9 quit
            app, console = self.build(folder, client, "10", "2", audio, "", "9", transcriber=transcriber)
            app.run_interactive(make_setup("live"))
            output = "\n".join(console.shown)
            self.assertIn('Heard: "Selamat pagi semuanya"', output)
            self.assertIn("1 translated, 0 already done, 0 failed", output)
            self.assertEqual(transcriber.calls, [(b"fake-audio", Language.INDONESIAN)])
            with open(os.path.join(folder, "records.json"), encoding="utf-8") as handle:
                record = json.load(handle)[0]
            self.assertEqual((record["input_type"], record["speaker"]), ("voice", "B"))
            self.assertEqual(record["transcript"], "Selamat pagi semuanya")
            self.assertNotIn("fake-audio", json.dumps(record), "the audio itself is never stored")
            self.assertNotIn(b"fake-audio", client.calls[0][1].encode(), "the AI only ever receives text")

    def test_the_user_can_correct_what_was_heard_before_it_is_translated(self):
        with TempDir() as folder:
            audio = self.audio_file(folder)
            client = ScriptedClient(ScriptedClient.json_reply())
            app, console = self.build(folder, client, "10", "1", audio, "The price is $4,800 per ton", "9",
                                      transcriber=FakeTranscriber(Transcription("the price is four eight hundred")))
            app.run_interactive(make_setup("live"))
            self.assertIn("$4,800 per ton", client.calls[0][1])
            self.assertNotIn("four eight hundred", client.calls[0][1])

    def test_cancelling_or_failing_voice_input_translates_nothing_and_keeps_running(self):
        with TempDir() as folder:
            audio = self.audio_file(folder)
            notes = self.audio_file(folder, "notes.txt")
            client = ScriptedClient(ScriptedClient.json_reply())
            transcriber = FakeTranscriber(Transcription("Hello there"))
            # cancel at the confirmation, a file that is not audio, Enter at the file prompt, then quit
            app, console = self.build(folder, client, "10", "1", audio, "/cancel",
                                      "10", "1", notes, "10", "1", "", "9", transcriber=transcriber)
            app.run_interactive(make_setup("live"))
            output = "\n".join(console.shown)
            self.assertNotIn("translated", output)
            self.assertIn("does not look like an audio file", output)
            self.assertEqual(client.calls, [])
            self.assertEqual(len(transcriber.calls), 1, "only the real audio file was transcribed")
            self.assertIn("Goodbye.", output)

    def test_without_the_speech_library_the_app_still_starts_and_option_10_explains_the_problem(self):
        with TempDir() as folder:
            audio = self.audio_file(folder)
            client = ScriptedClient(ScriptedClient.json_reply())
            with mock.patch.dict(sys.modules, {"faster_whisper": None}):  # simulates "pip install" not done
                WhisperTranscriber._shared_models.clear()
                # 10 voice (fails: no library), then 1 = type a sentence, speaker 1, the sentence, 9 quit
                app, console = self.build(folder, client, "10", "1", audio, "1", "1", "Typed sentences still work", "9")
                app.run_interactive(make_setup("live"))
            output = "\n".join(console.shown)
            self.assertIn("pip install faster-whisper", output)
            self.assertIn("1 translated", output, "typing keeps working after the voice problem")
            self.assertIn("Goodbye.", output)

    def test_invalid_menu_input_and_eof_do_not_crash(self):
        with TempDir() as folder:
            app, console = self.build(folder, FailingClient(), "zzz")
            app.run_interactive(make_setup())
            self.assertIn("Goodbye.", console.shown[-1])

    def test_batch_processes_input_files_by_name(self):
        with TempDir() as folder:
            os.makedirs(os.path.join(folder, "input"))
            with open(os.path.join(folder, "input", "standup.txt"), "w") as handle:
                handle.write("A: Good morning\nB: Selamat pagi")
            client = ScriptedClient(ScriptedClient.json_reply())
            app, console = self.build(folder, client)
            app.run_batch(make_setup())
            output = "\n".join(console.shown)
            self.assertIn("2 translated", output)
            self.assertIn("=== Meeting: standup ===", output)

    def test_batch_without_files_and_with_failing_ai(self):
        with TempDir() as folder:
            app, console = self.build(folder, FailingClient())
            app.run_batch(make_setup())
            self.assertIn("no .json or .txt files", console.shown[-1])
            os.makedirs(os.path.join(folder, "input"))
            with open(os.path.join(folder, "input", "x.txt"), "w") as handle:
                handle.write("A: hi")
            app2, console2 = self.build(folder, FailingClient())
            app2._pipeline._ai = AIManager(FailingClient(), sleep=lambda s: None)  # no real waiting
            app2.run_batch(make_setup())
            self.assertIn("1 failed", "\n".join(console2.shown))

    def test_main_without_api_key_exits_with_message(self):
        with TempDir() as folder:
            old = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "LOG_FILE")}
            os.environ["LOG_FILE"] = os.path.join(folder, "app.log")
            try:
                self.assertEqual(Application.main([], env_file=os.path.join(folder, "no.env")), 1)
            finally:
                os.environ.pop("LOG_FILE", None)
                for key, value in old.items():
                    if value is not None:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
