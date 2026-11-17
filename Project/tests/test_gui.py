import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # the GUI tests need streamlit; skip cleanly if it is not installed
    AppTest = None

from tests.fake_ai import FailingClient, ScriptedClient
from tests.gui_support import FakeServicesHolder, script_with_key, script_without_key
from tests.helpers import saved


def texts(at):
    """Every piece of visible text on the page, in one string."""
    parts = [m.value for m in at.markdown] + [t.value for t in at.text] + [e.value for e in at.error]
    parts += [w.value for w in at.warning] + [s.value for s in at.success] + [i.value for i in at.info]
    return "\n".join(parts)


def button(at, label):
    return next(b for b in at.button if b.label == label)


@unittest.skipIf(AppTest is None, "streamlit is not installed")
class StreamlitGuiTests(unittest.TestCase):
    def tearDown(self):
        FakeServicesHolder.shutdown()

    def start(self, client=None, records=None, with_key=True):
        FakeServicesHolder.reset(client or ScriptedClient(ScriptedClient.json_reply()), records)
        at = AppTest.from_function(script_with_key if with_key else script_without_key, default_timeout=20)
        return at.run()

    def submit_sentence(self, at, text):
        at.text_area[0].input(text)
        button(at, "Translate").click()
        return at.run()

    def finish_job(self, at):
        if "job" in at.session_state:
            job = at.session_state["job"]
            self.assertTrue(job.wait(10))
            return at.run()
        return at

    def test_first_render_has_no_errors_and_shows_empty_state(self):
        at = self.start()
        self.assertEqual(len(at.exception), 0)
        self.assertIn("Nothing has been said", texts(at))
        self.assertEqual([t.label for t in at.tabs], ["Live", "Transcript & report", "Filter"])

    def test_typed_sentence_is_translated_in_the_background_and_shown(self):
        at = self.start(ScriptedClient(ScriptedClient.json_reply(translation="Selamat siang semua")))
        at = self.submit_sentence(at, "Good afternoon everyone")
        self.assertEqual(len(at.exception), 0)
        self.assertIsNotNone(at.session_state["job"])          # a Job was queued, page did not block
        at = self.finish_job(at)
        self.assertEqual(len(at.exception), 0)
        page = texts(at)
        self.assertIn("Selamat siang semua", page)
        self.assertIn("Good afternoon everyone", page)
        self.assertEqual(len(FakeServicesHolder.current.data), 1)

    def test_tense_sentence_shows_warning(self):
        client = ScriptedClient(ScriptedClient.json_reply(tone="angry", intensity=5, tone_confidence=0.95))
        at = self.start(client)
        self.submit_sentence(at, "This is unacceptable!")
        at = self.finish_job(at)
        self.assertTrue(any("angry tone" in w.value for w in at.warning))

    def test_empty_sentence_shows_validation_error(self):
        at = self.start()
        at = self.submit_sentence(at, "   ")
        self.assertTrue(any("empty" in e.value for e in at.error))
        self.assertEqual(len(FakeServicesHolder.current.data), 0)

    def test_missing_api_key_is_reported(self):
        at = self.start(with_key=False)
        at = self.submit_sentence(at, "hello")
        self.assertTrue(any("API key" in e.value for e in at.error))
        self.assertEqual(len(FakeServicesHolder.current.data), 0)

    def test_ai_failure_is_reported_not_a_crash(self):
        at = self.start(FailingClient())
        self.submit_sentence(at, "hello")
        at = self.finish_job(at)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(FakeServicesHolder.current.data.all(), [])

    def test_existing_records_show_in_transcript_report_and_filter(self):
        records = [saved(1, "first", tone="angry"), saved(2, "second", speaker="B", tone="happy")]
        at = self.start(records=records)
        self.assertEqual(len(at.exception), 0)
        self.assertIn("Meeting report: m1", texts(at))
        self.assertIn("first", texts(at))
        self.assertEqual(len(at.dataframe), 1)
        self.assertEqual(len(at.dataframe[0].value), 2)
        tone_box = next(m for m in at.multiselect if m.label == "Tone")
        tone_box.select("angry")
        at = at.run()
        self.assertEqual(len(at.dataframe[0].value), 1)
        self.assertEqual(len(at.exception), 0)

    def test_filter_or_mode(self):
        records = [saved(1, "first", tone="angry"), saved(2, "second", speaker="B", tone="happy")]
        at = self.start(records=records)
        next(m for m in at.multiselect if m.label == "Tone").select("angry")
        next(m for m in at.multiselect if m.label == "Speaker").select("Mitra")
        at = at.run()
        self.assertEqual(len(at.dataframe[0].value), 0)   # AND: angry AND Mitra
        next(r for r in at.radio if r.label.startswith("When several")).set_value("Any of them (OR)")
        at = at.run()
        self.assertEqual(len(at.dataframe[0].value), 2)   # OR

    def test_a_voice_transcript_can_be_edited_and_translated(self):
        """AppTest cannot record audio, so the transcript is put into the session as 'Transcribe' would."""
        at = self.start(ScriptedClient(ScriptedClient.json_reply(translation="Good morning everyone")))
        at.session_state["voice_transcript"] = "Selamat pagi"
        at.run()
        box = next(t for t in at.text_area if t.label.startswith("Transcript"))
        self.assertEqual(box.value, "Selamat pagi")
        box.input("Selamat pagi semuanya")
        button(at, "Translate transcript").click()
        at.run()
        at = self.finish_job(at)
        self.assertEqual(len(at.exception), 0)
        record = FakeServicesHolder.current.data.all()[0]
        self.assertEqual((record.utterance.input_type, record.utterance.transcript), ("voice", "Selamat pagi semuanya"))
        self.assertEqual(at.session_state["voice_counter"], 1)          # the recorder was reset for the next sentence
        self.assertFalse(any(t.label.startswith("Transcript") for t in at.text_area))

    def test_new_meeting_button_changes_meeting_name(self):
        at = self.start()
        before = at.session_state["meeting_name"]
        button(at, "Start a new meeting").click()
        at = at.run()
        self.assertNotEqual(at.session_state["meeting_name"], before)
        self.assertTrue(at.session_state["meeting_name"].startswith("meeting-"))


if __name__ == "__main__":
    unittest.main()
