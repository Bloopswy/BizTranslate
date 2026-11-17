"""Services: the long-lived objects the GUI shares between Streamlit reruns."""

from __future__ import annotations

from typing import Optional

from ..ai_layer import AIClient, AIManager, GeminiClient
from ..background import BackgroundProcessor
from ..config import RuleSettings, Settings
from ..data_layer import DataManager, RepositoryFactory
from ..io_layer import MeetingFileReader, SpeechTranscriber, WhisperTranscriber
from ..logic_layer import LogicManager
from ..pipeline import MeetingPipeline


class Services:
    """The managers, the pipeline and the background worker, built once and reused.

    Streamlit re-runs the whole script on every click, so anything that must survive
    (records in memory, the worker thread, running jobs) lives in one Services object.
    """

    def __init__(self, settings: Settings, data: DataManager, logic: LogicManager,
                 pipeline: MeetingPipeline, background: BackgroundProcessor, reader: MeetingFileReader,
                 transcriber: Optional[SpeechTranscriber] = None):
        self.settings = settings
        self.data = data
        self.logic = logic
        self.pipeline = pipeline
        self.background = background
        self.reader = reader
        self.transcriber = transcriber  # None = voice input is switched off

    @classmethod
    def create(cls, settings: Settings, api_key: Optional[str] = None, ai_client: Optional[AIClient] = None,
               transcriber: Optional[SpeechTranscriber] = None) -> "Services":
        """`ai_client` and `transcriber` let tests substitute fakes for the live API and the Whisper model."""
        client = ai_client or GeminiClient(api_key if api_key is not None else settings.api_key, settings.model)
        data = DataManager(RepositoryFactory.for_path(settings.data_path))
        data.load()
        logic = LogicManager(RuleSettings.load(settings.rules_path))
        pipeline = MeetingPipeline(AIManager(client), logic, data)
        return cls(settings, data, logic, pipeline, BackgroundProcessor(pipeline),
                   MeetingFileReader(settings.input_dir), transcriber or WhisperTranscriber(settings.whisper_model))
