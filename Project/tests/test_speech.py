import sys
import threading
import time
import unittest
from unittest import mock

from meeting_translator.config import Settings
from meeting_translator.exceptions import SpeechError, SpeechUnavailableError, TranscriptionError
from meeting_translator.io_layer import SpeechTranscriber, Transcription, WhisperTranscriber
from meeting_translator.models import Language
from tests.fake_speech import FakeTranscriber, FakeWhisperModel


class TranscriptionTests(unittest.TestCase):
    def test_is_empty_for_silence_and_blank_text(self):
        self.assertTrue(Transcription("").is_empty)
        self.assertTrue(Transcription("   ", Language.ENGLISH).is_empty)
        self.assertFalse(Transcription("Hello", Language.ENGLISH).is_empty)

    def test_is_immutable(self):
        with self.assertRaises(Exception):
            Transcription("Hello").text = "changed"


class SpeechInterfaceTests(unittest.TestCase):
    def test_interface_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            SpeechTranscriber()

    def test_any_engine_can_replace_whisper(self):
        """Open/closed: a new engine is just another subclass; callers only know the interface."""
        class ShoutingTranscriber(SpeechTranscriber):
            def transcribe(self, audio, language=None):
                return Transcription(audio.decode().upper(), language)

        engines = [ShoutingTranscriber(), FakeTranscriber(Transcription("FAKE", Language.ENGLISH))]
        for engine in engines:
            self.assertIsInstance(engine.transcribe(b"fake", Language.ENGLISH), Transcription)

    def test_fake_transcriber_records_calls_raises_errors_and_repeats_the_last_result(self):
        fake = FakeTranscriber(Transcription("one"), TranscriptionError("bad"))
        self.assertEqual(fake.transcribe(b"a", Language.CHINESE).text, "one")
        for _ in range(2):
            with self.assertRaises(TranscriptionError):
                fake.transcribe(b"b")
        self.assertEqual(fake.calls[0], (b"a", Language.CHINESE))
        self.assertEqual(len(fake.calls), 3)


class WhisperTranscriberTests(unittest.TestCase):
    def setUp(self):
        WhisperTranscriber._shared_models.clear()

    tearDown = setUp

    @staticmethod
    def make(model=None, name="tiny"):
        loads = []

        def loader(model_name):
            loads.append(model_name)
            return model or FakeWhisperModel()

        return WhisperTranscriber(name, loader), loads

    def test_transcribes_with_the_speakers_language_as_a_hint(self):
        model = FakeWhisperModel(texts=(" Selamat ", "pagi semuanya "), language="id")
        transcriber, _ = self.make(model)
        result = transcriber.transcribe(b"audio-bytes", Language.INDONESIAN)
        self.assertEqual(result, Transcription("Selamat pagi semuanya", Language.INDONESIAN))
        self.assertEqual(len(model.calls), 1)
        options = model.calls[0]
        self.assertEqual((options["language"], options["audio"]), ("id", b"audio-bytes"))
        self.assertEqual((options["beam_size"], options["temperature"], options["vad_filter"]), (5, 0.0, True))

    def test_each_language_has_its_whisper_code(self):
        model = FakeWhisperModel()
        transcriber, _ = self.make(model)
        for language, code in ((Language.ENGLISH, "en"), (Language.INDONESIAN, "id"), (Language.CHINESE, "zh")):
            self.assertEqual(transcriber.transcribe(b"x", language).language, language)
            self.assertEqual(model.calls[-1]["language"], code)

    def test_auto_detect_is_limited_to_the_three_supported_languages(self):
        # Whisper's own best guess is Malay; of our three languages Indonesian is the likeliest.
        model = FakeWhisperModel(language="ms", probabilities=[("ms", 0.5), ("id", 0.4), ("en", 0.1)],
                                 texts_by_language={None: ["salah"], "id": ["Selamat", "pagi"]})
        transcriber, _ = self.make(model)
        result = transcriber.transcribe(b"x")
        self.assertEqual(result, Transcription("Selamat pagi", Language.INDONESIAN))
        self.assertEqual([call["language"] for call in model.calls], [None, "id"])

    def test_auto_detect_keeps_the_first_pass_when_it_is_already_supported(self):
        model = FakeWhisperModel(language="zh", probabilities=[("zh", 0.9), ("en", 0.05)], texts=["你好"])
        transcriber, _ = self.make(model)
        self.assertEqual(transcriber.transcribe(b"x"), Transcription("你好", Language.CHINESE))
        self.assertEqual(len(model.calls), 1)

    def test_auto_detect_of_an_unsupported_language_gives_no_language(self):
        model = FakeWhisperModel(language="fr", probabilities=[("fr", 0.9), ("de", 0.05)], texts=["Bonjour"])
        transcriber, _ = self.make(model)
        result = transcriber.transcribe(b"x")
        self.assertEqual((result.text, result.language), ("Bonjour", None))

    def test_pick_supported(self):
        self.assertEqual(WhisperTranscriber.pick_supported([("fr", 0.9), ("zh", 0.05), ("en", 0.02)]), "zh")
        self.assertIsNone(WhisperTranscriber.pick_supported([("fr", 0.9)]))
        self.assertIsNone(WhisperTranscriber.pick_supported(None))

    def test_auto_detect_with_allowed_languages_ignores_other_languages_and_low_margin(self):
        # Chinese is highest overall, but only English and Indonesian are allowed in this meeting.
        model = FakeWhisperModel(
            language="zh",
            probabilities=[("zh", 0.6), ("id", 0.32), ("en", 0.08)],
            texts_by_language={None: ["salah"], "id": ["Selamat pagi"]},
        )
        transcriber, _ = self.make(model)
        result = transcriber.transcribe(b"x", allowed_languages=(Language.ENGLISH, Language.INDONESIAN))
        self.assertEqual(result, Transcription("Selamat pagi", Language.INDONESIAN))

        # Margin too narrow (0.26 vs 0.24) -> uncertain, returns None for language.
        ambiguous = FakeWhisperModel(
            language="en",
            probabilities=[("en", 0.26), ("id", 0.24), ("zh", 0.50)],
            texts=["um"],
        )
        transcriber2, _ = self.make(ambiguous)
        result2 = transcriber2.transcribe(b"x", allowed_languages=(Language.ENGLISH, Language.INDONESIAN))
        self.assertEqual(result2, Transcription("um", None))

    def test_auto_detect_uses_cjk_fallback_when_chinese_is_allowed(self):
        model = FakeWhisperModel(
            language="en",
            probabilities=[("en", 0.26), ("zh", 0.24)],
            texts=["你好朋友"],
        )
        transcriber, _ = self.make(model)
        result = transcriber.transcribe(b"x", allowed_languages=(Language.ENGLISH, Language.CHINESE))
        self.assertEqual(result, Transcription("你好朋友", Language.CHINESE))

    def test_silence_gives_an_empty_transcription_not_an_error(self):
        transcriber, _ = self.make(FakeWhisperModel(texts=()))
        self.assertTrue(transcriber.transcribe(b"x", Language.ENGLISH).is_empty)

    def test_empty_and_oversized_audio_are_refused_before_the_model_is_loaded(self):
        transcriber, loads = self.make()
        with self.assertRaises(TranscriptionError) as empty:
            transcriber.transcribe(b"")
        self.assertIn("empty", str(empty.exception))
        with mock.patch("meeting_translator.io_layer.speech.MAX_AUDIO_BYTES", 10):
            with self.assertRaises(TranscriptionError) as big:
                transcriber.transcribe(b"x" * 11)
        self.assertIn("larger than", str(big.exception))
        self.assertEqual(loads, [])

    def test_missing_library_is_a_clear_speech_unavailable_error(self):
        with mock.patch.dict(sys.modules, {"faster_whisper": None}):  # simulates "not installed"
            with self.assertRaises(SpeechUnavailableError) as raised:
                WhisperTranscriber("base").transcribe(b"x")
        self.assertIn("pip install faster-whisper", str(raised.exception))

    def test_model_that_cannot_be_loaded_explains_the_download(self):
        def failing_loader(name):
            raise OSError("no internet")

        with self.assertRaises(SpeechUnavailableError) as raised:
            WhisperTranscriber("small", failing_loader).transcribe(b"x")
        message = str(raised.exception)
        self.assertIn("small", message)
        self.assertIn("no internet", message)
        self.assertIn("download", message)

    def test_unreadable_audio_is_a_transcription_error(self):
        transcriber, _ = self.make(FakeWhisperModel(error=RuntimeError("not an audio file")))
        with self.assertRaises(TranscriptionError) as raised:
            transcriber.transcribe(b"x", Language.ENGLISH)
        self.assertIn("not an audio file", str(raised.exception))

    def test_every_failure_is_a_speech_error(self):
        transcriber, _ = self.make(FakeWhisperModel(error=RuntimeError("boom")))
        with self.assertRaises(SpeechError):
            transcriber.transcribe(b"x")
        with self.assertRaises(SpeechError):
            transcriber.transcribe(b"")
        self.assertTrue(issubclass(SpeechUnavailableError, SpeechError))

    def test_the_model_is_loaded_once_per_instance(self):
        transcriber, loads = self.make()
        transcriber.transcribe(b"x", Language.ENGLISH)
        transcriber.transcribe(b"y", Language.ENGLISH)
        self.assertEqual(loads, ["tiny"])

    def test_default_loader_shares_one_model_between_instances(self):
        loads = []

        def counting_loader(name):
            loads.append(name)
            return FakeWhisperModel()

        with mock.patch.object(WhisperTranscriber, "_load_faster_whisper", staticmethod(counting_loader)):
            WhisperTranscriber("tiny").transcribe(b"x", Language.ENGLISH)
            WhisperTranscriber("tiny").transcribe(b"x", Language.ENGLISH)
            WhisperTranscriber("small").transcribe(b"x", Language.ENGLISH)
        self.assertEqual(loads, ["tiny", "small"])

    def test_concurrent_first_use_loads_the_model_only_once(self):
        loads, results = [], []

        def slow_loader(name):
            loads.append(name)
            time.sleep(0.05)  # long enough for the other threads to arrive while it loads
            return FakeWhisperModel()

        transcriber = WhisperTranscriber("tiny", slow_loader)
        threads = [threading.Thread(target=lambda: results.append(transcriber.transcribe(b"x", Language.ENGLISH).text))
                   for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(loads, ["tiny"])
        self.assertEqual(results, ["Hello there"] * 6)

    def test_model_name_comes_from_the_settings(self):
        self.assertEqual(WhisperTranscriber(Settings({"WHISPER_MODEL": "small"}).whisper_model).model_name, "small")
        self.assertEqual(WhisperTranscriber().model_name, "base")


if __name__ == "__main__":
    unittest.main()
