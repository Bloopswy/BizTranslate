import os
import unittest

from meeting_translator.data_layer import (CsvRecordRepository, DataManager, JsonRecordRepository, RecordQuery,
                                           RecordRepository, RepositoryFactory)
from meeting_translator.models import Outcome
from tests.fake_storage import MemoryRepository
from tests.helpers import TempDir, saved


def sample():
    return [
        saved(1, "a", speaker="A", tone="angry", detected_language="English", outcome=Outcome.TENSION),
        saved(2, "b", speaker="B", tone="happy", detected_language="Chinese", outcome=Outcome.ACCEPT),
        saved(3, "c", speaker="B", tone="angry", detected_language="Chinese", outcome=Outcome.CHECK),
        saved(4, "d", speaker="A", tone="neutral", detected_language="Indonesian", meeting="m2"),
    ]


class RepositoryContractTests(unittest.TestCase):
    """The same behaviour is required of every file repository (Liskov Substitution)."""

    repositories = (JsonRecordRepository, CsvRecordRepository)

    def for_each(self, check):
        for repo_class in self.repositories:
            with TempDir() as folder:
                suffix = ".csv" if repo_class is CsvRecordRepository else ".json"
                check(repo_class, TempDir.join(folder, "data", "records" + suffix))

    def test_save_and_load_across_runs(self):
        def check(repo_class, path):
            records = sample()
            self.assertTrue(repo_class(path).save_all(records))
            loaded = repo_class(path).load_all()  # a "new run": new repository object
            self.assertEqual([r.to_dict() for r in loaded], [r.to_dict() for r in records], repo_class.__name__)
        self.for_each(check)

    def test_missing_file_means_no_records(self):
        self.for_each(lambda repo_class, path: self.assertEqual(repo_class(path).load_all(), []))

    def test_corrupt_file_is_moved_aside_not_fatal(self):
        def check(repo_class, path):
            os.makedirs(os.path.dirname(path))
            with open(path, "wb") as handle:
                handle.write(b"\xff\xfe garbage {{{ not a records file")
            self.assertEqual(repo_class(path).load_all(), [])
            self.assertTrue(os.path.exists(path + ".corrupt"))
            self.assertFalse(os.path.exists(path))
        self.for_each(check)

    def test_unwritable_location_returns_false(self):
        def check(repo_class, path):
            blocker = os.path.dirname(path)
            os.makedirs(os.path.dirname(blocker), exist_ok=True)
            with open(blocker, "w") as handle:  # a FILE where the folder should be
                handle.write("x")
            self.assertFalse(repo_class(path).save_all(sample()))
        self.for_each(check)

    def test_unicode_survives(self):
        def check(repo_class, path):
            record = saved(1, "大家下午好，我们很期待。")
            repo_class(path).save_all([record])
            self.assertEqual(repo_class(path).load_all()[0].transcript, "大家下午好，我们很期待。")
        self.for_each(check)

    def test_all_are_record_repositories(self):
        for repo_class in self.repositories:
            self.assertTrue(issubclass(repo_class, RecordRepository))


class JsonSpecificTests(unittest.TestCase):
    def test_wrong_shape_is_corrupt_and_bad_records_are_skipped(self):
        with TempDir() as folder:
            path = TempDir.join(folder, "r.json")
            with open(path, "w") as handle:
                handle.write('{"not": "a list"}')
            self.assertEqual(JsonRecordRepository(path).load_all(), [])
            self.assertTrue(os.path.exists(path + ".corrupt"))

            good = saved(1).to_dict()
            import json
            with open(path, "w") as handle:
                json.dump([good, {"id": "x"}, {**good, "tone": "bored"}], handle)
            self.assertEqual(len(JsonRecordRepository(path).load_all()), 1)

    def test_csv_without_id_column_is_corrupt(self):
        with TempDir() as folder:
            path = TempDir.join(folder, "r.csv")
            with open(path, "w") as handle:
                handle.write("a,b\n1,2\n")
            self.assertEqual(CsvRecordRepository(path).load_all(), [])
            self.assertTrue(os.path.exists(path + ".corrupt"))


class FactoryTests(unittest.TestCase):
    def test_chooses_by_extension_and_is_extensible(self):
        self.assertIsInstance(RepositoryFactory.for_path("x.csv"), CsvRecordRepository)
        self.assertIsInstance(RepositoryFactory.for_path("x.json"), JsonRecordRepository)
        self.assertIsInstance(RepositoryFactory.for_path("x.unknown"), JsonRecordRepository)
        RepositoryFactory.register(".mem", MemoryRepository)  # any class taking one argument
        try:
            self.assertIsInstance(RepositoryFactory.for_path("x.mem"), MemoryRepository)
        finally:
            RepositoryFactory._by_extension.pop(".mem")


class DataManagerTests(unittest.TestCase):
    def manager(self, records=None):
        manager = DataManager(MemoryRepository(records if records is not None else sample()))
        manager.load()
        return manager

    def test_load_and_save_use_the_injected_repository(self):
        repo = MemoryRepository(sample())
        manager = DataManager(repo)
        self.assertEqual(manager.load(), 4)
        manager.add(saved(5, "e"))
        self.assertTrue(manager.save())
        self.assertEqual(len(repo.records), 5)

    def test_add_replaces_same_id(self):
        manager = self.manager()
        manager.add(saved(1, "a"))
        self.assertEqual(len(manager), 4)

    def test_meetings_and_ordering(self):
        manager = self.manager(list(reversed(sample())))
        self.assertEqual(manager.meetings(), ["m1", "m2"])
        self.assertEqual([r.seq for r in manager.meeting_records("m1")], [1, 2, 3])

    def test_next_sequence(self):
        manager = self.manager()
        self.assertEqual(manager.next_sequence("m1"), 4)
        self.assertEqual(manager.next_sequence("new"), 1)

    def test_last_sentences_and_latest_with_context(self):
        manager = self.manager()
        self.assertEqual([r.seq for r in manager.last_sentences("m1", 2)], [2, 3])
        self.assertEqual(manager.last_sentences("m1", 0), [])
        latest, previous = manager.latest_with_context("m1", 2)
        self.assertEqual((latest.seq, [r.seq for r in previous]), (3, [1, 2]))
        self.assertEqual(manager.latest_with_context("nothing", 3), (None, []))

    def test_find_by_id(self):
        manager = self.manager()
        record = sample()[0]
        self.assertEqual(manager.find_by_id(record.id).id, record.id)
        self.assertIsNone(manager.find_by_id("nope"))


class QueryTests(unittest.TestCase):
    def ids(self, query):
        manager = DataManager(MemoryRepository(sample()))
        manager.load()
        return [r.transcript for r in manager.query(query)]

    def test_single_criteria(self):
        self.assertEqual(self.ids(RecordQuery(tones=["angry"])), ["a", "c"])
        self.assertEqual(self.ids(RecordQuery(languages=["Chinese"])), ["b", "c"])
        self.assertEqual(self.ids(RecordQuery(target_languages=["Indonesian"])), ["a", "d"])  # spoken by Acme (A)
        self.assertEqual(self.ids(RecordQuery(speakers=["Mitra"])), ["b", "c"])
        self.assertEqual(self.ids(RecordQuery(outcome="CHECK")), ["c"])
        self.assertEqual(self.ids(RecordQuery(meeting="m2")), ["d"])

    def test_and_versus_or(self):
        both = dict(tones=["angry"], languages=["Chinese"])
        self.assertEqual(self.ids(RecordQuery(**both, match="all")), ["c"])
        self.assertEqual(self.ids(RecordQuery(**both, match="any")), ["a", "b", "c"])

    def test_no_criteria_returns_everything_and_narrowing_always_applies(self):
        self.assertEqual(len(self.ids(RecordQuery())), 4)
        self.assertEqual(self.ids(RecordQuery(tones=["angry"], match="any", outcome="TENSION")), ["a"])


if __name__ == "__main__":
    unittest.main()
