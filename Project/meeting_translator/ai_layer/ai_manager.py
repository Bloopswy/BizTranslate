"""AIManager: every utterance passes through here."""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from ..exceptions import AIError
from ..models import AIAnalysis, ProcessedRecord, Utterance
from .client import AIClient
from .parsing import ResponseParser, ResponseValidator
from .prompts import PromptBuilder


class AIManager:
    """Builds the prompt, calls the AI, parses and validates the answer, retrying on failure.

    The AIClient is injected (aggregation - it lives on its own and can be a fake in tests).
    The prompt builder, parser and validator are created here and owned by the manager
    (composition - they have no life outside it).
    """

    def __init__(self, client: AIClient, max_attempts: int = 3, sleep: Callable[[float], None] = time.sleep):
        self._client = client
        self._max_attempts = max(1, max_attempts)
        self._sleep = sleep
        self._prompts = PromptBuilder()
        self._parser = ResponseParser()
        self._validator = ResponseValidator()

    def analyse(self, utterance: Utterance, context: Optional[List[ProcessedRecord]] = None) -> Optional[AIAnalysis]:
        """Send one sentence (plus earlier sentences as context) through the AI.

        Returns the validated analysis, or None if every attempt failed. Never raises:
        connection errors, timeouts, malformed JSON and schema violations are logged and retried.
        """
        system = self._prompts.system_instruction(utterance.listener.language.value)
        prompt = self._prompts.user_prompt(utterance, context)

        for attempt in range(1, self._max_attempts + 1):
            try:
                raw_text = self._client.generate(system, prompt)
                return self._validator.validate(self._parser.parse(raw_text))
            except AIError as error:
                logging.warning("AI attempt %d/%d for record %s failed: %s",
                                attempt, self._max_attempts, utterance.id, error)
            if attempt < self._max_attempts:
                self._sleep(2 ** attempt)  # 2s, 4s backoff (also eases rate limits)

        logging.error("Giving up on record %s after %d attempts", utterance.id, self._max_attempts)
        return None

    def summarize(self, records: List[ProcessedRecord]) -> Optional[str]:
        """Ask the AI for a concise executive summary of the meeting."""
        if not records:
            return None
        transcript_lines = [
            f"{r.speaker_name} ({r.speaker_language}): {r.transcript} -> {r.translation}"
            for r in records
        ]
        system = (
            "You are an executive business meeting secretary. In 3 to 4 concise bullet points, "
            "summarize this bilingual business meeting's key discussion topics, counterpart proposals, "
            "and consensus reached."
        )
        prompt = "Meeting dialogue:\n" + "\n".join(transcript_lines)
        try:
            return self._client.generate(system, prompt).strip()
        except AIError as error:
            logging.warning("AI summarization failed: %s", error)
            return None
