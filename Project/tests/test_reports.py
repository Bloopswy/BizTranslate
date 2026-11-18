import unittest

from meeting_translator.models import Outcome
from meeting_translator.reports import (AttentionSection, ExecutiveSummarySection, MeetingReport,
                                        OutcomeSection, OverviewSection, ReportSection,
                                        SpeakerSection, ToneSection)
from tests.helpers import saved


def records():
    return [
        saved(1, "calm", speaker="A", tone="neutral", intensity=1, score=10),
        saved(2, "furious!", speaker="B", tone="angry", intensity=5, score=80, outcome=Outcome.TENSION),
        saved(3, "unsure", speaker="B", tone="angry", intensity=3, score=60, outcome=Outcome.CHECK),
        saved(4, "thanks", speaker="A", tone="grateful", intensity=2, score=20),
    ]


class ReportTests(unittest.TestCase):
    def test_sections_content(self):
        r = records()
        self.assertIn("Sentences: 4", OverviewSection().lines(r))
        self.assertIn("Average attention score: 42.5 / 100", OverviewSection().lines(r))
        outcome_lines = OutcomeSection().lines(r)
        self.assertTrue(any(l.startswith("TENSION") and "25%" in l for l in outcome_lines))
        self.assertTrue(any("Strongest tone on average: angry" in l for l in ToneSection().lines(r)))
        speakers = SpeakerSection().lines(r)
        self.assertEqual(speakers, ["Acme: 2 sentence(s), average score 15.0, 0 tense moment(s)",
                                    "Mitra: 2 sentence(s), average score 70.0, 1 tense moment(s)"])
        attention = AttentionSection(top=1).lines(r)
        self.assertEqual(len(attention), 1)
        self.assertIn("furious!", attention[0])

    def test_nothing_flagged(self):
        self.assertIn("ran smoothly", AttentionSection().lines([saved(1)])[0])

    def test_full_report_and_empty(self):
        text = MeetingReport().render(records(), "Title")
        for heading in ("Overview", "Outcomes", "Tone", "Speakers", "Moments needing attention"):
            self.assertIn(heading, text)
        self.assertIn("No sentences to report on", MeetingReport().render([]))

    def test_executive_summary_rule_based(self):
        r = records()
        section = ExecutiveSummarySection()
        lines = section.lines(r)
        self.assertTrue(any("Participants" in l for l in lines))
        self.assertTrue(any("Climate" in l for l in lines))

    def test_executive_summary_provided(self):
        r = records()
        section = ExecutiveSummarySection(summary="AI generated executive summary\nSecond line")
        lines = section.lines(r)
        self.assertEqual(lines, ["AI generated executive summary", "Second line"])

    def test_open_closed_custom_section(self):
        class Shout(ReportSection):
            title = "Shout"

            def lines(self, records):
                return ["HELLO %d" % len(records)]

        text = MeetingReport([Shout()]).render(records())
        self.assertIn("HELLO 4", text)
        self.assertNotIn("Overview", text)


if __name__ == "__main__":
    unittest.main()
