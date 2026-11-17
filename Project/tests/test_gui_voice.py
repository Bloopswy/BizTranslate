"""The voice-input part of the Streamlit GUI, tested WITHOUT Streamlit.

A fake `streamlit` module is put in place while the GUI module is imported, so the real StreamlitGui
code runs against stand-in widgets. (tests/test_gui.py covers the page with Streamlit's own AppTest, which
needs streamlit installed; AppTest cannot record audio, so this file covers the record/transcribe step.)
"""

import base64
import importlib
import sys
import unittest
from unittest import mock

from meeting_translator.config import Settings
from meeting_translator.exceptions import TranscriptionError
from meeting_translator.io_layer import Transcription
from meeting_translator.models import Language
from tests.fake_ai import ScriptedClient
from tests.fake_speech import FakeTranscriber
from tests.gui_support import FakeServicesHolder
from tests.helpers import make_setup

GUI_MODULE = "meeting_translator.gui.streamlit_app"


def make_fake_streamlit():
    """A stand-in for the streamlit module: every widget is a mock that returns 'nothing happened'."""
    st = mock.MagicMock(name="streamlit")
    st.session_state = {}
    st.cache_resource.side_effect = lambda *args, **kwargs: (lambda function: function)
    st.columns.side_effect = lambda spec: [mock.MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.radio.return_value = "A"
    st.checkbox.return_value = False
    st.text_area.return_value = ""
    st.button.return_value = False
    st.form_submit_button.return_value = False
    st.file_uploader.return_value = None
    st.audio_input.return_value = None
    return st


class VoiceGuiTests(unittest.TestCase):
    def setUp(self):
        self.st = make_fake_streamlit()
        patched = {
            "streamlit": self.st,
            "streamlit.components": self.st.components,
            "streamlit.components.v1": self.st.components.v1,
        }
        with mock.patch.dict(sys.modules, patched):
            sys.modules.pop(GUI_MODULE, None)
            self.module = importlib.import_module(GUI_MODULE)
        self.addCleanup(sys.modules.pop, GUI_MODULE, None)  # never leak the fake into other tests
        self.addCleanup(FakeServicesHolder.shutdown)
        self.transcriber = FakeTranscriber(Transcription("Selamat pagi", Language.INDONESIAN))
        self.client = ScriptedClient(ScriptedClient.json_reply(translation="Good morning"))
        self.setup = make_setup("live")

    def gui(self, transcriber="default"):
        services = FakeServicesHolder.reset(self.client, transcriber=self.transcriber if transcriber == "default" else transcriber)
        gui = self.module.StreamlitGui(Settings({}), lambda api_key: services)
        gui._services = services
        return gui, services

    def press(self, *labels):
        self.st.button.side_effect = lambda label, **kwargs: label in labels

    def submit(self, *labels):
        self.st.form_submit_button.side_effect = lambda label, **kwargs: label in labels

    @staticmethod
    def recording(data=b"wav-bytes"):
        return mock.MagicMock(getvalue=lambda: data)

    def messages(self, widget):
        return " ".join(str(call.args[0]) for call in widget.call_args_list if call.args)

    # ----- record -> transcribe -----
    def test_transcribing_uses_the_speakers_language_and_keeps_the_text_for_editing(self):
        gui, _ = self.gui()
        self.st.radio.return_value = "B"
        self.st.audio_input.return_value = self.recording()
        self.press("Transcribe")
        gui._live_tab(self.setup, "key")
        self.assertEqual(self.transcriber.calls, [(b"wav-bytes", Language.INDONESIAN)])  # party B speaks Indonesian
        self.assertEqual(self.st.session_state["voice_transcript"], "Selamat pagi")
        self.assertFalse(self.st.error.called)

    def test_the_recorder_is_only_shown_with_a_transcriber_and_nothing_happens_before_recording(self):
        gui, _ = self.gui()
        gui._live_tab(self.setup, "key")
        self.assertEqual(self.st.audio_input.call_args.kwargs["key"], "voice_audio_0")
        self.assertEqual(self.transcriber.calls, [], "no recording, no transcription")
        self.assertNotIn("voice_transcript", self.st.session_state)

        self.st.audio_input.reset_mock()
        gui, _ = self.gui(transcriber=None)
        gui._live_tab(self.setup, "key")
        self.assertFalse(self.st.audio_input.called)
        self.assertIn("not available", self.messages(self.st.caption))

    def test_silence_gives_a_warning_and_no_transcript(self):
        self.transcriber.results = [Transcription("  ")]
        gui, _ = self.gui()
        self.st.audio_input.return_value = self.recording()
        self.press("Transcribe")
        gui._live_tab(self.setup, "key")
        self.assertIn("No speech was detected", self.messages(self.st.warning))
        self.assertNotIn("voice_transcript", self.st.session_state)

    def test_speech_errors_are_shown_and_never_crash_the_page(self):
        self.transcriber.results = [TranscriptionError("Could not transcribe that recording (bad audio).")]
        gui, _ = self.gui()
        self.st.audio_input.return_value = self.recording()
        self.press("Transcribe")
        gui._live_tab(self.setup, "key")
        self.assertIn("bad audio", self.messages(self.st.error))
        self.assertNotIn("voice_transcript", self.st.session_state)

    # ----- edit -> translate -----
    def test_the_edited_transcript_is_translated_as_a_voice_sentence_and_the_form_resets(self):
        gui, services = self.gui()
        self.st.session_state["voice_transcript"] = "Selamat pagi"
        self.st.text_area.return_value = "Selamat pagi semuanya"           # what the user changed it to
        self.submit("Translate transcript")
        gui._live_tab(self.setup, "key")

        job = self.st.session_state["job"]
        self.assertTrue(job.wait(10))
        record = services.data.all()[0]
        self.assertEqual((record.utterance.input_type, record.utterance.transcript), ("voice", "Selamat pagi semuanya"))
        self.assertEqual(record.translation, "Good morning")
        self.assertNotIn("voice_transcript", self.st.session_state)
        self.assertEqual(self.st.session_state["voice_counter"], 1)
        self.st.rerun.assert_called_once()
        self.assertNotIn(b"wav", self.client.calls[0][1].encode(), "the AI receives text only")

        self.st.audio_input.reset_mock()
        self.submit()
        gui._live_tab(self.setup, "key")
        self.assertEqual(self.st.audio_input.call_args.kwargs["key"], "voice_audio_1")  # a fresh, empty recorder

    def test_without_an_api_key_the_transcript_is_kept_so_nothing_is_lost(self):
        gui, services = self.gui()
        self.st.session_state["voice_transcript"] = "Selamat pagi"
        self.st.text_area.return_value = "Selamat pagi"
        self.submit("Translate transcript")
        gui._live_tab(self.setup, "")
        self.assertEqual(self.st.session_state["voice_transcript"], "Selamat pagi")
        self.assertNotIn("job", self.st.session_state)
        self.assertEqual(len(services.data), 0)
        self.assertFalse(self.st.rerun.called)
        self.assertTrue(self.st.error.called)

    def test_an_emptied_transcript_is_refused_and_kept(self):
        gui, services = self.gui()
        self.st.session_state["voice_transcript"] = "Selamat pagi"
        self.st.text_area.return_value = "   "
        self.submit("Translate transcript")
        gui._live_tab(self.setup, "key")
        self.assertEqual(self.st.session_state["voice_transcript"], "Selamat pagi")
        self.assertEqual(len(services.data), 0)
        self.assertTrue(self.st.error.called)
        self.assertFalse(self.st.rerun.called)

    def test_auto_detect_picks_the_matching_party_without_a_language_hint(self):
        gui, services = self.gui()
        self.st.checkbox.side_effect = lambda label, **kwargs: label.startswith("Auto-detect")
        self.st.radio.return_value = "A"  # Party A is English; recording is Indonesian (Party B)
        self.st.audio_input.return_value = self.recording()
        self.press("Transcribe")
        gui._live_tab(self.setup, "key")

        self.assertEqual(self.transcriber.calls, [(b"wav-bytes", None)])
        self.assertEqual(self.st.session_state["voice_speaker_id"], "B")
        self.assertIn("Indonesian", self.st.session_state["voice_detection_note"][1])

        # Submitting the transcript uses the detected speaker ("B"), then clears detection state.
        self.press()
        self.st.text_area.return_value = "Selamat pagi"
        self.submit("Translate transcript")
        gui._live_tab(self.setup, "key")
        self.assertTrue(self.st.session_state["job"].wait(10))
        self.assertEqual(services.data.all()[0].utterance.speaker_id, "B")
        self.assertNotIn("voice_speaker_id", self.st.session_state)
        self.assertNotIn("voice_detection_note", self.st.session_state)

    def test_auto_detect_falls_back_to_selected_speaker_when_language_is_unmatched(self):
        self.transcriber.results = [Transcription("Bonjour", None)]
        gui, _ = self.gui()
        self.st.checkbox.side_effect = lambda label, **kwargs: label.startswith("Auto-detect")
        self.st.radio.return_value = "A"
        self.st.audio_input.return_value = self.recording()
        self.press("Transcribe")
        gui._live_tab(self.setup, "key")

        self.assertEqual(self.st.session_state["voice_speaker_id"], "A")
        self.assertEqual(self.st.session_state["voice_detection_note"][0], "warning")

    def test_continuous_mode_transcribes_detects_speaker_and_submits_job(self):
        gui, services = self.gui()
        self.st.checkbox.side_effect = lambda label, **kwargs: label.startswith("Continuous")
        self.st.radio.return_value = "A"
        payload = {"seq": 1, "audio_b64": base64.b64encode(b"wav-bytes").decode("ascii")}
        with mock.patch.object(gui, "_continuous_mic", return_value=payload):
            gui._live_tab(self.setup, "key")

        self.assertEqual(self.transcriber.calls, [(b"wav-bytes", None)])
        self.assertEqual(self.transcriber.allowed_calls, [(Language.ENGLISH, Language.INDONESIAN)])
        self.assertTrue(self.st.session_state["job"].wait(10))
        record = services.data.all()[0]
        self.assertEqual(record.utterance.speaker_id, "B")
        self.assertEqual(record.utterance.input_type, "voice")
        self.assertIn("Indonesian", self.st.session_state["voice_continuous_status"])

        # Re-rendering with the same seq does not re-transcribe or duplicate.
        with mock.patch.object(gui, "_continuous_mic", return_value=payload):
            gui._live_tab(self.setup, "key")
        self.assertEqual(len(self.transcriber.calls), 1)

    def test_continuous_mode_ignores_silence_without_creating_a_job(self):
        self.transcriber.results = [Transcription("   ")]
        gui, services = self.gui()
        self.st.checkbox.side_effect = lambda label, **kwargs: label.startswith("Continuous")
        payload = {"seq": 2, "audio_b64": base64.b64encode(b"silence").decode("ascii")}
        with mock.patch.object(gui, "_continuous_mic", return_value=payload):
            gui._live_tab(self.setup, "key")
        self.assertNotIn("job", self.st.session_state)
        self.assertEqual(len(services.data), 0)

    def test_typed_sentences_still_work_and_are_marked_as_text(self):
        gui, services = self.gui()
        self.st.text_area.return_value = "Good afternoon everyone"
        self.submit("Translate")
        gui._live_tab(self.setup, "key")
        self.assertTrue(self.st.session_state["job"].wait(10))
        self.assertEqual(services.data.all()[0].utterance.input_type, "text")
        self.assertFalse(self.st.rerun.called, "typing does not need the voice reset")


class ServicesTranscriberTests(unittest.TestCase):
    def test_services_create_builds_the_whisper_transcriber_from_the_settings(self):
        from meeting_translator.gui.services import Services
        from meeting_translator.io_layer import WhisperTranscriber
        services = Services.create(Settings({"WHISPER_MODEL": "small"}), "key", ai_client=ScriptedClient(ScriptedClient.json_reply()))
        try:
            self.assertIsInstance(services.transcriber, WhisperTranscriber)
            self.assertEqual(services.transcriber.model_name, "small")
        finally:
            services.background.shutdown()

    def test_a_fake_transcriber_can_be_injected(self):
        from meeting_translator.gui.services import Services
        fake = FakeTranscriber()
        services = Services.create(Settings({}), "key", ai_client=ScriptedClient(ScriptedClient.json_reply()), transcriber=fake)
        try:
            self.assertIs(services.transcriber, fake)
        finally:
            services.background.shutdown()


if __name__ == "__main__":
    unittest.main()
