"""Tests for language-based voice speaker detection across models and CLI IO."""

import os
import tempfile
import unittest

from meeting_translator.io_layer import Console, IOManager, MeetingFileReader, Transcription
from meeting_translator.models import Language, MeetingSetup, Party
from tests.fake_speech import FakeTranscriber


class PartyForLanguageTests(unittest.TestCase):
    def test_returns_unique_matching_party(self):
        setup = MeetingSetup("m1", Party("Acme", Language.ENGLISH), Party("Mitra", Language.INDONESIAN))
        self.assertEqual(setup.party_for_language(Language.ENGLISH), "A")
        self.assertEqual(setup.party_for_language(Language.INDONESIAN), "B")
        self.assertIsNone(setup.party_for_language(Language.CHINESE))
        self.assertIsNone(setup.party_for_language(None))

    def test_returns_none_when_both_parties_speak_the_same_language(self):
        setup = MeetingSetup("m1", Party("A", Language.ENGLISH), Party("B", Language.ENGLISH))
        self.assertIsNone(setup.party_for_language(Language.ENGLISH))


class VoiceDetectionCliTests(unittest.TestCase):
    def _make_io(self, inputs, transcriber):
        outputs = []
        console = Console(
            input_fn=lambda prompt="": inputs.pop(0) if inputs else "",
            output_fn=outputs.append,
        )
        io = IOManager(console, MeetingFileReader("input"), transcriber=transcriber)
        return io, outputs

    def test_prompt_voice_speaker_supports_auto_detect(self):
        setup = MeetingSetup("m1", Party("Acme", Language.ENGLISH), Party("Mitra", Language.INDONESIAN))
        io, _ = self._make_io(["3"], FakeTranscriber())
        self.assertEqual(io.prompt_voice_speaker(setup), "AUTO")

    def test_transcribe_audio_with_detection_selects_matching_party(self):
        setup = MeetingSetup("m1", Party("Acme", Language.ENGLISH), Party("Mitra", Language.INDONESIAN))
        transcriber = FakeTranscriber(Transcription("Selamat pagi", Language.INDONESIAN))
        io, outputs = self._make_io([], transcriber)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(b"fake-wav")
            path = tmp.name
        try:
            result = io.transcribe_audio_with_detection(setup, path, speaker_id=None)
        finally:
            os.remove(path)
        self.assertEqual(result, ("Selamat pagi", "B"))
        self.assertEqual(transcriber.calls, [(b"fake-wav", None)])
        self.assertEqual(transcriber.allowed_calls, [(Language.ENGLISH, Language.INDONESIAN)])
        self.assertTrue(any("Detected Indonesian" in line for line in outputs))

    def test_transcribe_audio_with_detection_prompts_when_ambiguous(self):
        setup = MeetingSetup("m1", Party("Acme", Language.ENGLISH), Party("Mitra", Language.ENGLISH))
        transcriber = FakeTranscriber(Transcription("Hello", Language.ENGLISH))
        io, _ = self._make_io(["2"], transcriber)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(b"fake-wav")
            path = tmp.name
        try:
            result = io.transcribe_audio_with_detection(setup, path, speaker_id=None)
        finally:
            os.remove(path)
        self.assertEqual(result, ("Hello", "B"))


if __name__ == "__main__":
    unittest.main()
