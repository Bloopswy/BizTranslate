import threading
import unittest

from meeting_translator.ai_layer import AIManager
from meeting_translator.background import BackgroundProcessor, Job
from meeting_translator.data_layer import DataManager
from meeting_translator.logic_layer import LogicManager
from meeting_translator.pipeline import MeetingPipeline, ProcessStatus
from tests.fake_ai import ScriptedClient
from tests.fake_storage import MemoryRepository
from tests.helpers import saved, utterance


class GatedClient(ScriptedClient):
    """Blocks inside generate() until released, so tests can observe a job 'in progress'."""

    def __init__(self, *replies):
        super().__init__(*replies)
        self.entered = threading.Event()
        self.release = threading.Event()

    def generate(self, system_instruction, user_prompt):
        self.entered.set()
        self.release.wait(5)
        return super().generate(system_instruction, user_prompt)


def build(client, repo=None):
    data = DataManager(repo or MemoryRepository())
    data.load()
    pipeline = MeetingPipeline(AIManager(client, sleep=lambda s: None), LogicManager(), data)
    return BackgroundProcessor(pipeline), data


def sentences(count):
    return [utterance("sentence %d" % i, position=i) for i in range(1, count + 1)]


class BackgroundProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processors = []

    def tearDown(self):
        for processor in self.processors:
            processor.shutdown()

    def make(self, client, repo=None):
        processor, data = build(client, repo)
        self.processors.append(processor)
        return processor, data

    def test_submit_returns_immediately_and_job_completes(self):
        client = GatedClient(ScriptedClient.json_reply())
        processor, data = self.make(client)
        job = processor.submit(sentences(3))
        self.assertTrue(client.entered.wait(5))
        self.assertFalse(job.finished)           # the caller was NOT blocked while the AI "works"
        self.assertEqual(job.total, 3)
        client.release.set()
        self.assertTrue(job.wait(5))
        self.assertEqual(job.counts["processed"], 3)
        self.assertEqual((job.done, job.progress), (3, 1.0))
        self.assertEqual(len(data), 3)

    def test_runs_in_a_different_thread(self):
        seen = []

        class Spy(ScriptedClient):
            def generate(self, system_instruction, user_prompt):
                seen.append(threading.current_thread().name)
                return super().generate(system_instruction, user_prompt)

        processor, _ = self.make(Spy(ScriptedClient.json_reply()))
        processor.submit(sentences(1)).wait(5)
        self.assertEqual(seen, ["translator-worker"])
        self.assertNotEqual(seen[0], threading.current_thread().name)

    def test_sentences_stay_in_order_across_jobs(self):
        client = ScriptedClient(*[ScriptedClient.json_reply(translation="T%d" % i) for i in range(1, 6)])
        processor, data = self.make(client)
        first = processor.submit(sentences(2))
        second = processor.submit([utterance("sentence 3", position=3), utterance("sentence 4", position=4)])
        self.assertTrue(first.wait(5) and second.wait(5))
        self.assertEqual([r.seq for r in data.meeting_records("m1")], [1, 2, 3, 4])
        self.assertEqual([r.transcript for r in data.meeting_records("m1")],
                         ["sentence 1", "sentence 2", "sentence 3", "sentence 4"])
        self.assertIn("sentence 2", client.calls[2][1])  # context of #3 contains #2: order preserved

    def test_cancel_stops_before_next_sentence(self):
        client = GatedClient(ScriptedClient.json_reply())
        processor, data = self.make(client)
        job = processor.submit(sentences(4))
        self.assertTrue(client.entered.wait(5))
        job.cancel()
        client.release.set()
        self.assertTrue(job.wait(5))
        self.assertEqual(job.counts["processed"], 1)
        self.assertEqual(job.counts[Job.CANCELLED], 3)
        self.assertEqual(len(data), 1)

    def test_failures_are_counted_and_worker_survives(self):
        from tests.fake_ai import FailingClient
        processor, _ = self.make(FailingClient())
        job = processor.submit(sentences(2))
        self.assertTrue(job.wait(5))
        self.assertEqual(job.counts["failed"], 2)
        self.assertTrue(processor.running)
        self.assertTrue(processor.submit([]).wait(5))  # still accepts work

    def test_unexpected_exception_does_not_kill_the_worker(self):
        class Exploding(ScriptedClient):
            def generate(self, system_instruction, user_prompt):
                if "boom" in user_prompt:
                    raise RuntimeError("bug")
                return super().generate(system_instruction, user_prompt)

        processor, data = self.make(Exploding(ScriptedClient.json_reply()))
        job = processor.submit([utterance("boom", position=1), utterance("fine", position=2)])
        self.assertTrue(job.wait(5))
        self.assertEqual((job.counts["failed"], job.counts["processed"]), (1, 1))

    def test_duplicates_are_skipped(self):
        processor, _ = self.make(ScriptedClient(ScriptedClient.json_reply()))
        batch = sentences(2)
        processor.submit(batch).wait(5)
        job = processor.submit(batch)
        job.wait(5)
        self.assertEqual(job.counts[ProcessStatus.SKIPPED.value], 2)

    def test_empty_job_finishes_at_once(self):
        processor, _ = self.make(ScriptedClient(ScriptedClient.json_reply()))
        job = processor.submit([])
        self.assertTrue(job.wait(5))
        self.assertEqual(job.progress, 1.0)

    def test_shutdown_stops_worker_and_submit_restarts_it(self):
        processor, _ = self.make(ScriptedClient(ScriptedClient.json_reply()))
        processor.submit(sentences(1)).wait(5)
        self.assertTrue(processor.running)
        processor.shutdown()
        self.assertFalse(processor.running)
        self.assertTrue(processor.submit(sentences(1)).wait(5))


class DataManagerThreadSafetyTests(unittest.TestCase):
    def test_concurrent_adds_and_reads_lose_nothing(self):
        data = DataManager(MemoryRepository())
        errors = []

        def writer(offset):
            try:
                for i in range(50):
                    data.add(saved(offset + i, "t%d-%d" % (offset, i)))
                    data.all()
                    data.meetings()
            except Exception as error:  # noqa: BLE001
                errors.append(error)

        threads = [threading.Thread(target=writer, args=(n * 100,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(data), 200)
        self.assertTrue(data.save())


if __name__ == "__main__":
    unittest.main()
