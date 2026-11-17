import os
import unittest
from meeting_translator.ai_layer import AIManager
from meeting_translator.data_layer import DataManager, JsonRecordRepository
from meeting_translator.logic_layer import LogicManager
from meeting_translator.models import Outcome
from meeting_translator.pipeline import MeetingPipeline, PipelineObserver, ProcessStatus
from tests.fake_ai import FailingClient, ScriptedClient
from tests.fake_storage import MemoryRepository
from tests.helpers import TempDir, utterance


class Recorder(PipelineObserver):
    def __init__(self):
        self.processed, self.failed = [], []

    def on_processed(self, record):
        self.processed.append(record)

    def on_failed(self, utterance):
        self.failed.append(utterance)

def make_pipeline(client, repo=None, observer=None):
    data = DataManager(repo or MemoryRepository())
    data.load()
    pipeline = MeetingPipeline(AIManager(client, sleep=lambda s: None), LogicManager(), data,
                               [observer] if observer else [])
    return pipeline, data

class PipelineTests(unittest.TestCase):
    def test_ai_output_flows_to_logic_and_storage(self):
        repo = MemoryRepository()
        observer = Recorder()
        pipeline, data = make_pipeline(
            ScriptedClient(ScriptedClient.json_reply(tone="angry", intensity=5, tone_confidence=0.95)), repo, observer)
        self.assertEqual(pipeline.process(utterance("Unacceptable!")), ProcessStatus.PROCESSED)
        self.assertEqual(data.all()[0].outcome, Outcome.TENSION.value)
        self.assertEqual(len(repo.records), 1)  # saved
        self.assertEqual(len(observer.processed), 1)

    def test_duplicate_is_skipped_without_calling_ai(self):
        client = ScriptedClient(ScriptedClient.json_reply())
        pipeline, _ = make_pipeline(client)
        u = utterance("Same")
        pipeline.process(u)
        self.assertEqual(pipeline.process(u), ProcessStatus.SKIPPED)
        self.assertEqual(len(client.calls), 1)

    def test_ai_failure_is_reported_not_raised_and_nothing_is_saved(self):
        observer = Recorder()
        repo = MemoryRepository()
        pipeline, data = make_pipeline(FailingClient(), repo, observer)
        self.assertEqual(pipeline.process(utterance()), ProcessStatus.FAILED)
        self.assertEqual((len(data), repo.saves, len(observer.failed)), (0, 0, 1))

    def test_every_record_goes_through_the_ai(self):
        client = ScriptedClient(ScriptedClient.json_reply())
        pipeline, _ = make_pipeline(client)
        pipeline.process_many([utterance("one", position=1), utterance("two", position=2), utterance("three", position=3)])
        self.assertEqual(len(client.calls), 3)

    def test_counts_and_sequence_and_context(self):
        client = ScriptedClient(ScriptedClient.json_reply(translation="T1"), ScriptedClient.json_reply(translation="T2"))
        pipeline, data = make_pipeline(client)
        us = [utterance("first", position=1), utterance("second", position=2), utterance("first", position=1)]
        counts = pipeline.process_many(us)
        self.assertEqual(counts, {"processed": 2, "skipped": 1, "failed": 0})
        self.assertEqual([r.seq for r in data.meeting_records("m1")], [1, 2])
        self.assertIn("first", client.calls[1][1])   # earlier sentence sent as context
        self.assertIn("T1", client.calls[1][1])

    def test_save_failure_does_not_lose_the_record_in_memory(self):
        pipeline, data = make_pipeline(ScriptedClient(ScriptedClient.json_reply()), MemoryRepository(fail_save=True))
        self.assertEqual(pipeline.process(utterance()), ProcessStatus.PROCESSED)
        self.assertEqual(len(data), 1)

    def test_records_persist_across_runs(self):
        with TempDir() as folder:
            path = os.path.join(folder, "records.json")
            pipeline, _ = make_pipeline(ScriptedClient(ScriptedClient.json_reply()), JsonRecordRepository(path))
            u = utterance("persist me")
            pipeline.process(u)
            client2 = ScriptedClient(ScriptedClient.json_reply())
            pipeline2, data2 = make_pipeline(client2, JsonRecordRepository(path))
            self.assertEqual(len(data2), 1)
            self.assertEqual(pipeline2.process(u), ProcessStatus.SKIPPED)
            self.assertEqual(client2.calls, [])

if __name__ == "__main__":
    unittest.main()
