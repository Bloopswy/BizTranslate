from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Iterable, List, Optional

from .ai_layer import AIManager
from .data_layer import DataManager
from .logic_layer import LogicManager
from .models import ProcessedRecord, Utterance

class ProcessStatus(str, Enum):
    PROCESSED = "processed"
    SKIPPED = "skipped"  # already processed (e.g. the same file read twice)
    FAILED = "failed"    # AI gave up; logged, and can be retried later

class PipelineObserver(ABC):
    """Interface: told about each result. The pipeline never prints - the IO layer observes it."""

    @abstractmethod
    def on_processed(self, record: ProcessedRecord) -> None:
        """A sentence was translated, routed and saved."""

    @abstractmethod
    def on_failed(self, utterance: Utterance) -> None:
        """The AI could not process a sentence."""

class MeetingPipeline:
    """Collaborates with the three other managers (association) - none of them knows the others."""

    def __init__(self, ai: AIManager, logic: LogicManager, data: DataManager,
                 observers: Optional[Iterable[PipelineObserver]] = None):
        self._ai = ai
        self._logic = logic
        self._data = data
        self._observers: List[PipelineObserver] = list(observers or [])

    @property
    def ai(self) -> AIManager:
        return self._ai

    def add_observer(self, observer: PipelineObserver) -> None:
        self._observers.append(observer)

    def process(self, utterance: Utterance) -> ProcessStatus:
        """Run one sentence through the pipeline. The previous few sentences of the same
        meeting go to the AI as context."""
        if self._data.find_by_id(utterance.id) is not None:
            return ProcessStatus.SKIPPED
        context = self._data.last_sentences(utterance.meeting, self._logic.settings.context_sentences)
        analysis = self._ai.analyse(utterance, context)
        if analysis is None:
            for observer in self._observers:
                observer.on_failed(utterance)
            return ProcessStatus.FAILED
        decision = self._logic.route(utterance, analysis)
        record = ProcessedRecord(utterance, analysis, decision, self._data.next_sequence(utterance.meeting))
        self._data.add(record)
        if not self._data.save():  # keep going: the record is still in memory
            logging.error("Record %s processed but could not be saved", record.id)
        for observer in self._observers:
            observer.on_processed(record)
        return ProcessStatus.PROCESSED

    def process_many(self, utterances: Iterable[Utterance]) -> Dict[str, int]:
        """Process sentences in order, saving after each one so progress is never lost."""
        counts = {status.value: 0 for status in ProcessStatus}
        for utterance in utterances:
            counts[self.process(utterance).value] += 1
        return counts
