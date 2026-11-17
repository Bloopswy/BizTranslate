"""Fake storage held in memory."""

from meeting_translator.data_layer import RecordRepository


class MemoryRepository(RecordRepository):
    def __init__(self, records=None, fail_save=False):
        self.records = list(records or [])
        self.fail_save = fail_save
        self.saves = 0

    def load_all(self):
        return list(self.records)

    def save_all(self, records):
        self.saves += 1
        if self.fail_save:
            return False
        self.records = list(records)
        return True
