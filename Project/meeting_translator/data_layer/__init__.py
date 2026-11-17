"""Data layer (system memory across runs): querying, storage back-ends and the DataManager."""
from .data_manager import DataManager
from .query import RecordQuery
from .repositories import CsvRecordRepository, FileRecordRepository, JsonRecordRepository, RecordRepository, RepositoryFactory

__all__ = ["DataManager", "RecordQuery", "RecordRepository", "FileRecordRepository",
           "JsonRecordRepository", "CsvRecordRepository", "RepositoryFactory"]
