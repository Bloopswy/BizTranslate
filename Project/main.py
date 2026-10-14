"""Entry point for the terminal version. Wires the four layers together:

    user / file -> io_manager -> ai_manager -> logic_manager -> data_manager

Usage:
    python main.py                 interactive menu
    python main.py --batch         translate every meeting file in the input folder, then exit
    python main.py --meeting standup --a-name Acme --a-language English --b-name Mitra --b-language Indonesian

(The web version is app.py:  streamlit run app.py)
"""

import argparse
import logging
import os
import sys

import ai_manager
import data_manager
import io_manager
import logic_manager

LOG_PATH = os.environ.get("LOG_FILE", os.path.join("data", "app.log"))

def setup_logging():
    """Log to a file only, so all terminal output stays in io_manager."""
    folder = os.path.dirname(LOG_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    
def process_record(raw_record, records, api_key):
    """Run one sentence through AI -> logic -> data.

    The previous few sentences of the same meeting go to the AI as context. Returns
    (updated_records, status) where status is 'processed', 'skipped' or 'failed'.
    """
    if data_manager.find_by_id(records, raw_record["id"]) is not None:
        return records, "skipped"  # already processed (e.g. the same file read twice)

    meeting = raw_record["meeting"]
    context = data_manager.last_sentences(records, meeting, logic_manager.CONTEXT_SENTENCES)
    ai_fields = ai_manager.analyse_record(raw_record, api_key, context)
    if ai_fields is None:
        return records, "failed"  # logged by ai_manager; can be retried

    decision = logic_manager.route({**raw_record, **ai_fields})
    full_record = {**raw_record, **ai_fields, **decision, "seq": data_manager.next_sequence(records, meeting)}
    return data_manager.add_record(records, full_record), "processed"


def process_records(raw_records, records, api_key, tz_name=None):
    """Process many sentences in order, saving after each one so progress is never lost."""
    counts = {"processed": 0, "skipped": 0, "failed": 0}
    for raw_record in raw_records:
        records, status = process_record(raw_record, records, api_key)
        counts[status] += 1
        if status == "processed":
            data_manager.save_records(records)
            io_manager.show_sentence(data_manager.find_by_id(records, raw_record["id"]), tz_name)
        elif status == "failed":
            io_manager.show_error("AI translation failed for a sentence from %s (see the log); continuing"
                                  % raw_record.get("speaker_name", "?"))
    io_manager.show_message(
        "\nDone: %(processed)d translated, %(skipped)d already done, %(failed)d failed." % counts
    )
    return records
