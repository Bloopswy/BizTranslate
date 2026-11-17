import unittest

from meeting_translator.exceptions import RecordFormatError, ValidationError
from meeting_translator.models import (ClockFormatter, Language, MeetingSetup, Outcome, Party, ProcessedRecord,
                                       Utterance)
from tests.helpers import make_setup, saved, utterance


class PartyTests(unittest.TestCase):
    def test_cleans_name_and_exposes_read_only_properties(self):
        party = Party("  Acme\n  Foods  ", "English")
        self.assertEqual(party.name, "Acme Foods")
        self.assertEqual(party.language, Language.ENGLISH)
        with self.assertRaises(AttributeError):
            party.name = "other"  # encapsulation: no setter

    def test_rejects_unknown_language(self):
        with self.assertRaises(ValidationError):
            Party("X", "Klingon")

    def test_equality(self):
        self.assertEqual(Party("A", "English"), Party("A", "English"))
        self.assertNotEqual(Party("A", "English"), Party("A", "Chinese"))


class MeetingSetupTests(unittest.TestCase):
    def test_from_dict_falls_back_on_bad_values(self):
        base = make_setup("base")
        setup = MeetingSetup.from_dict({"meeting": 5, "parties": {"A": {"name": "N", "language": "Nope"}}}, base)
        self.assertEqual(setup.meeting, "base")
        self.assertEqual(setup.party("A").name, "N")
        self.assertEqual(setup.party("A").language, Language.ENGLISH)
        self.assertEqual(setup.party("B"), base.party("B"))

    def test_listener_is_the_other_party(self):
        setup = make_setup()
        self.assertEqual(setup.listener_of("A").name, "Mitra")
        self.assertEqual(setup.listener_of("B").name, "Acme")

    def test_parties_are_shared_not_copied(self):
        a = Party("A", "English")
        setup = MeetingSetup("m", a, Party("B", "Chinese"))
        self.assertIs(setup.party("A"), a)  # aggregation: part exists independently


class UtteranceTests(unittest.TestCase):
    def test_create_sets_direction(self):
        u = utterance("Hello", "A")
        self.assertEqual(u.speaker.name, "Acme")
        self.assertEqual(u.listener.language, Language.INDONESIAN)

    def test_same_input_same_id_and_position_distinguishes(self):
        self.assertEqual(utterance("Hi", position=1).id, utterance("Hi", position=1).id)
        self.assertNotEqual(utterance("Hi", position=1).id, utterance("Hi", position=2).id)

    def test_validation_failures(self):
        setup = make_setup()
        for speaker, text in (("C", "hi"), ("A", ""), ("A", "   "), ("A", None), ("A", "x" * 2001)):
            with self.assertRaises(ValidationError, msg=repr((speaker, text))):
                Utterance.create(setup, speaker, text)

    def test_bad_timestamp_becomes_empty_and_live_gets_now(self):
        self.assertEqual(Utterance.create(make_setup(), "A", "hi", "garbage").timestamp, "")
        self.assertTrue(Utterance.create(make_setup(), "a", "hi").timestamp)

    def test_dict_round_trip(self):
        u = utterance("Hello")
        self.assertEqual(Utterance.from_dict(u.to_dict()), u)


class ProcessedRecordTests(unittest.TestCase):
    def test_round_trip(self):
        record = saved(1, "hello")
        again = ProcessedRecord.from_dict(record.to_dict())
        self.assertEqual(again.to_dict(), record.to_dict())
        self.assertEqual(again.outcome, "ACCEPT")

    def test_migrates_old_records(self):
        data = saved(1).to_dict()
        data["english_translation"] = data.pop("translation")
        data["urgency"] = data.pop("intensity")
        data["outcome"] = "ESCALATE"
        for key in ("meeting", "speaker_name", "seq"):
            data.pop(key)
        record = ProcessedRecord.from_dict(data)
        self.assertEqual(record.outcome, Outcome.TENSION.value)
        self.assertEqual(record.meeting, "earlier-records")
        self.assertEqual(record.seq, 0)

    def test_bad_data_raises_record_format_error(self):
        good = saved(1).to_dict()
        for broken in ("not a dict", {**good, "tone": "ecstatic"}, {**good, "outcome": "???"},
                       {k: v for k, v in good.items() if k != "transcript"}, {**good, "score": "abc"},
                       {**good, "reasons": "text"}):
            with self.assertRaises(RecordFormatError, msg=repr(broken)):
                ProcessedRecord.from_dict(broken)


class ClockTests(unittest.TestCase):
    def test_formats_in_zone_and_handles_garbage(self):
        self.assertEqual(ClockFormatter.format("2026-10-14T09:00:05+00:00", "UTC"), "09:00:05")
        self.assertEqual(ClockFormatter.format("nonsense"), "--:--:--")
        self.assertEqual(ClockFormatter.format("2026-10-14T09:00:05", "UTC", with_date=True), "2026-10-14 09:00:05")
        self.assertEqual(ClockFormatter.format("2026-10-14T09:00:05+00:00", "No/Such_Zone"), "09:00:05")


if __name__ == "__main__":
    unittest.main()
