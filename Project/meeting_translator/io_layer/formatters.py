"""Presentation: turning records into text, and exporters (polymorphic output formats)."""

from __future__ import annotations

import csv
import io
import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import List, Optional

from ..models import ClockFormatter, ProcessedRecord


class RecordFormatter:
    """Readable text views of records, in one time zone."""

    def __init__(self, tz_name: Optional[str] = None):
        self._tz = tz_name

    @staticmethod
    def direction(record: ProcessedRecord) -> str:
        return "%s (%s) -> %s (%s)" % (record.speaker_name, record.speaker_language,
                                       record.listener_name, record.target_language)

    def sentence(self, record: ProcessedRecord) -> str:
        """Detailed multi-line view of one sentence."""
        return "\n".join([
            "[%s] %s  [%s]" % (ClockFormatter.format(record.timestamp, self._tz), self.direction(record), record.outcome),
            "    Said       : %s" % record.transcript,
            "    Translated : %s" % record.translation,
            "    Tone       : %s (confidence %.2f), intensity %s/5, attention score %s/100" % (
                record.tone, record.analysis.tone_confidence, record.intensity, record.score),
            "    Note       : %s" % "; ".join(record.reasons),
        ])

    def short_sentence(self, record: ProcessedRecord) -> str:
        """Compact two-line view used for the 'previous sentences' list."""
        return "[%s] %s (%s): %s\n           -> %s" % (
            ClockFormatter.format(record.timestamp, self._tz), record.speaker_name,
            record.speaker_language, record.transcript, record.translation)

    def conversation(self, latest: Optional[ProcessedRecord], previous: List[ProcessedRecord]) -> str:
        if latest is None:
            return "Nothing has been said in this meeting yet."
        lines = ["--- Latest translation ---", self.sentence(latest),
                 "\n--- Previous %d sentences ---" % len(previous) if previous else "\n(no earlier sentences)"]
        lines.extend(self.short_sentence(record) for record in previous)
        return "\n".join(lines)

    def transcript(self, records: List[ProcessedRecord]) -> str:
        if not records:
            return "No sentences."
        return "\n".join(self.short_sentence(record) for record in records)

    @staticmethod
    def summary(records: List[ProcessedRecord]) -> str:
        if not records:
            return "No records yet."
        lines = ["Total sentences: %d" % len(records)]
        for title, getter in (("By outcome", lambda r: r.outcome), ("By speaker", lambda r: r.speaker_name),
                              ("By language spoken", lambda r: r.detected_language), ("By tone", lambda r: r.tone)):
            counts = Counter(getter(r) for r in records)
            lines.append("%s: %s" % (title, ", ".join("%s=%d" % (name, counts[name]) for name in sorted(counts))))
        return "\n".join(lines)

    @staticmethod
    def safe_filename(text: str) -> str:
        """A file-name-friendly version of a meeting name."""
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("._") or "meeting"


class Exporter(ABC):
    """Interface: render records as text in some file format."""

    extension: str

    @abstractmethod
    def export(self, records: List[ProcessedRecord]) -> str:
        """The records as text."""


class CsvExporter(Exporter):
    extension = ".csv"
    COLUMNS = [
        "meeting", "seq", "timestamp", "speaker_name", "speaker_language", "listener_name", "target_language",
        "transcript", "translation", "detected_language", "language_confidence", "translation_confidence",
        "tone", "tone_confidence", "intensity", "score", "tone_reason", "outcome", "reasons", "input_type", "id",
    ]

    def export(self, records):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = record.to_dict()
            row["reasons"] = "; ".join(row["reasons"])
            writer.writerow(row)
        return buffer.getvalue()


class JsonExporter(Exporter):
    extension = ".json"

    def export(self, records):
        return json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2)


class TextExporter(Exporter):
    """Plain-text meeting minutes: one block per sentence with date and time."""

    extension = ".txt"

    def __init__(self, tz_name: Optional[str] = None):
        self._tz = tz_name

    def export(self, records):
        blocks = []
        for r in records:
            blocks.append("[%s] %s\n  Said: %s\n  Translation: %s\n  Tone: %s\n  Flag: %s" % (
                ClockFormatter.format(r.timestamp, self._tz, with_date=True), RecordFormatter.direction(r),
                r.transcript, r.translation, r.tone, r.outcome))
        return "\n\n".join(blocks) + ("\n" if blocks else "")


class SummaryPdfExporter:
    """Exports meeting summary text into a clean PDF document."""

    @staticmethod
    def export_pdf(title: str, text: str) -> bytes:
        try:
            import io
            import re
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                'DocTitle',
                parent=styles['Heading1'],
                fontSize=18,
                leading=22,
                textColor=colors.HexColor('#0f172a'),
                spaceAfter=6
            )
            sub_style = ParagraphStyle(
                'DocSub',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor('#64748b'),
                spaceAfter=14
            )
            body_style = ParagraphStyle(
                'DocBody',
                parent=styles['Normal'],
                fontSize=10,
                leading=15,
                textColor=colors.HexColor('#1e293b'),
                spaceAfter=8
            )

            story = [
                Paragraph("Executive Summary", title_style),
                Paragraph(f"Meeting: {title}", sub_style),
                Spacer(1, 10),
            ]

            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    story.append(Spacer(1, 6))
                else:
                    clean_line = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    clean_line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_line)
                    clean_line = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_line)
                    story.append(Paragraph(clean_line, body_style))

            doc.build(story)
            return buf.getvalue()
        except Exception:
            return SummaryPdfExporter._fallback_pdf(title, text)

    @staticmethod
    def _fallback_pdf(title: str, text: str) -> bytes:
        lines = [f"Meeting: {title}", ""] + text.splitlines()
        content_lines = ['BT', '/F1 16 Tf', '50 740 Td', '(Executive Summary) Tj', '/F1 10 Tf', '0 -25 Td']
        for line in lines[:35]:
            safe = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            content_lines.append(f'({safe}) Tj')
            content_lines.append('0 -15 Td')
        content_lines.append('ET')
        stream_content = '\n'.join(content_lines).encode('latin-1', errors='replace')
        stream_len = len(stream_content)

        pdf = bytearray()
        pdf.extend(b'%PDF-1.4\n')
        offsets = []

        def add_obj(body: bytes):
            offsets.append(len(pdf))
            pdf.extend(f'{len(offsets)} 0 obj\n'.encode('ascii'))
            pdf.extend(body)
            pdf.extend(b'\nendobj\n')

        add_obj(b'<< /Type /Catalog /Pages 2 0 R >>')
        add_obj(b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>')
        add_obj(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources 4 0 R >>')
        add_obj(b'<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>')
        add_obj(f'<< /Length {stream_len} >>\nstream\n'.encode('ascii') + stream_content + b'\nendstream')

        xref_offset = len(pdf)
        pdf.extend(f'xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n'.encode('ascii'))
        for off in offsets:
            pdf.extend(f'{off:010d} 00000 n \n'.encode('ascii'))
        pdf.extend(f'trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'.encode('ascii'))
        return bytes(pdf)
