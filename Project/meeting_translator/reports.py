from __future__ import annotations
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from typing import Iterable, List, Optional
from .models import ClockFormatter, Outcome, ProcessedRecord

class ReportSection(ABC):
    """One titled block of a report."""

    @property
    @abstractmethod
    def title(self) -> str:
        """Heading of the section."""

    @abstractmethod
    def lines(self, records: List[ProcessedRecord]) -> List[str]:
        """Body lines for these records."""

class OverviewSection(ReportSection):
    title = "Overview"

    def lines(self, records):
        stamps = sorted(r.timestamp for r in records if r.timestamp)
        average = sum(r.score for r in records) / len(records)
        lines = ["Sentences: %d" % len(records), "Average attention score: %.1f / 100" % average]
        if stamps:
            lines.append("From %s to %s" % (ClockFormatter.format(stamps[0], with_date=True),
                                            ClockFormatter.format(stamps[-1], with_date=True)))
        return lines

class OutcomeSection(ReportSection):
    title = "Outcomes"

    def lines(self, records):
        counts = Counter(r.outcome for r in records)
        return ["%-8s %3d  (%.0f%%)" % (o.value, counts[o.value], 100.0 * counts[o.value] / len(records))
                for o in Outcome]

class ToneSection(ReportSection):
    title = "Tone"

    def lines(self, records):
        counts = Counter(r.tone for r in records)
        lines = ["%-10s %3d" % (tone, number) for tone, number in counts.most_common()]
        intensity = defaultdict(list)
        for record in records:
            intensity[record.tone].append(record.intensity)
        strongest = max(intensity, key=lambda t: (sum(intensity[t]) / len(intensity[t]), t))
        lines.append("Strongest tone on average: %s (%.1f / 5)" % (strongest, sum(intensity[strongest]) / len(intensity[strongest])))
        return lines

class SpeakerSection(ReportSection):
    title = "Speakers"

    def lines(self, records):
        by_speaker = defaultdict(list)
        for record in records:
            by_speaker[record.speaker_name].append(record)
        lines = []
        for name in sorted(by_speaker):
            rows = by_speaker[name]
            tense = sum(1 for r in rows if r.outcome == Outcome.TENSION.value)
            lines.append("%s: %d sentence(s), average score %.1f, %d tense moment(s)"
                         % (name, len(rows), sum(r.score for r in rows) / len(rows), tense))
        return lines

class AttentionSection(ReportSection):
    """The highest-scoring sentences, so the reader knows where to look first."""

    title = "Moments needing attention"

    def __init__(self, top: int = 3):
        self._top = top

    def lines(self, records):
        flagged = [r for r in records if r.outcome in (Outcome.TENSION.value, Outcome.CHECK.value)]
        ranked = sorted(flagged, key=lambda r: (-r.score, r.timestamp, r.id))[:self._top]
        if not ranked:
            return ["Nothing flagged - the meeting ran smoothly."]
        return ["[%s] %s %s (score %d): %s" % (ClockFormatter.format(r.timestamp), r.outcome, r.speaker_name,
                                                r.score, r.transcript) for r in ranked]


class ExecutiveSummarySection(ReportSection):
    """Concise executive overview of meeting discussion, key points, and consensus."""

    title = "Executive Summary"

    def __init__(self, summary: Optional[str] = None):
        self._summary = summary

    def lines(self, records: List[ProcessedRecord]) -> List[str]:
        if not records:
            return ["No sentences recorded."]
        if self._summary and self._summary.strip():
            return [line.strip() for line in self._summary.strip().splitlines() if line.strip()]

        speakers = sorted({r.speaker_name for r in records})
        accepted = [r for r in records if r.outcome == Outcome.ACCEPT.value]
        tensions = sum(1 for r in records if r.outcome == Outcome.TENSION.value)
        rate = (len(accepted) / len(records)) * 100.0 if records else 0.0
        climate = "Constructive (no tension detected)" if tensions == 0 else f"{tensions} tense moment(s) flagged"

        lines = [
            f"Participants : {', '.join(speakers)}",
            f"Climate      : {climate} (Consensus: {rate:.0f}%)",
            "Key discussion points:",
        ]
        sample_records = accepted[:3] if accepted else records[:2]
        for r in sample_records:
            lines.append(f"  • {r.speaker_name}: \"{r.translation}\"")
        return lines


class MeetingReport:
    """Renders a list of sections over a list of records."""

    def __init__(self, sections: Optional[Iterable[ReportSection]] = None, summary: Optional[str] = None):
        self._sections = list(sections) if sections is not None else self.default_sections(summary)

    @staticmethod
    def analytics_sections() -> List[ReportSection]:
        return [
            OverviewSection(),
            OutcomeSection(),
            ToneSection(),
            SpeakerSection(),
            AttentionSection(),
        ]

    @staticmethod
    def default_sections(summary: Optional[str] = None) -> List[ReportSection]:
        return [
            ExecutiveSummarySection(summary),
            OverviewSection(),
            OutcomeSection(),
            ToneSection(),
            SpeakerSection(),
            AttentionSection(),
        ]

    def render(self, records: List[ProcessedRecord], title: str = "Meeting report") -> str:
        if not records:
            return "%s\n\nNo sentences to report on." % title
        blocks = [title, "=" * len(title)]
        for section in self._sections:
            blocks.append("")
            blocks.append(section.title)
            blocks.append("-" * len(section.title))
            blocks.extend(section.lines(records))
        return "\n".join(blocks) + "\n"
