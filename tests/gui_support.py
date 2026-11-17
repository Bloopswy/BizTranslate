"""Shared state for GUI tests: Streamlit re-runs the script, so the fake services live here."""

from meeting_translator.ai_layer import AIManager
from meeting_translator.background import BackgroundProcessor
from meeting_translator.config import Settings
from meeting_translator.data_layer import DataManager
from meeting_translator.gui.services import Services
from meeting_translator.io_layer import MeetingFileReader
from meeting_translator.logic_layer import LogicManager
from meeting_translator.pipeline import MeetingPipeline
from tests.fake_speech import FakeTranscriber
from tests.fake_storage import MemoryRepository

_DEFAULT = object()  # 'use a fake transcriber' (None means: no voice input at all)


class FakeServicesHolder:
    current = None

    @classmethod
    def reset(cls, client, records=None, input_dir="no-such-folder", transcriber=_DEFAULT):
        data = DataManager(MemoryRepository(records))
        data.load()
        logic = LogicManager()
        pipeline = MeetingPipeline(AIManager(client, sleep=lambda s: None), logic, data)
        cls.current = Services(Settings({}), data, logic, pipeline, BackgroundProcessor(pipeline),
                               MeetingFileReader(input_dir),
                               FakeTranscriber() if transcriber is _DEFAULT else transcriber)
        return cls.current

    @classmethod
    def shutdown(cls):
        if cls.current is not None:
            cls.current.background.shutdown()
            cls.current = None


def script_with_key():
    from meeting_translator.config import Settings
    from meeting_translator.gui.streamlit_app import StreamlitGui
    from tests.gui_support import FakeServicesHolder
    StreamlitGui(Settings({"GEMINI_API_KEY": "test-key"}), lambda key: FakeServicesHolder.current).run()


def script_without_key():
    from meeting_translator.config import Settings
    from meeting_translator.gui.streamlit_app import StreamlitGui
    from tests.gui_support import FakeServicesHolder
    StreamlitGui(Settings({}), lambda key: FakeServicesHolder.current).run()
