import json
import logging
import os

DEFAULT_DATA_PATH = os.environ.get("DATA_FILE", os.path.join("data", "records.json"))
LEGACY_MEETING = "earlier-records"
