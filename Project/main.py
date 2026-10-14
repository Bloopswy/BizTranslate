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
def load_raw_records_from_files(file_names, setup, name_meeting_after_file=False):
    """Read the chosen meeting files. Returns a de-duplicated list of raw sentence records.

    With name_meeting_after_file, a file that does not name its own meeting becomes a
    meeting called after the file (so batch runs are repeatable).
    """
    raw_records, seen = [], set()
    for name in file_names:
        file_setup = setup
        if name_meeting_after_file:
            stem = io_manager.clean_label(os.path.splitext(name)[0], setup["meeting"], io_manager.MAX_MEETING_CHARS)
            file_setup = {**setup, "meeting": stem}
        found, errors = io_manager.read_meeting_file(os.path.join(io_manager.INPUT_DIR, name), file_setup)
        for message in errors:
            io_manager.show_error(message)
        for record in found:
            if record["id"] not in seen:
                seen.add(record["id"])
                raw_records.append(record)
    return raw_records


def show_meeting_panel(records, meeting, tz_name=None):
    latest, previous = data_manager.latest_with_context(records, meeting, logic_manager.CONTEXT_SENTENCES)
    io_manager.show_conversation(latest, previous, tz_name)


def run_batch(records, api_key, setup, tz_name=None, name_meeting_after_file=True):
    files = io_manager.list_input_files()
    if not files:
        io_manager.show_error("no .json or .txt files found in the '%s' folder" % io_manager.INPUT_DIR)
        return records
    raw_records = load_raw_records_from_files(files, setup, name_meeting_after_file)
    records = process_records(raw_records, records, api_key, tz_name)
    meetings = []
    for raw_record in raw_records:
        if raw_record["meeting"] not in meetings:
            meetings.append(raw_record["meeting"])
    for meeting in meetings:
        io_manager.show_message("\n=== Meeting: %s ===" % meeting)
        show_meeting_panel(records, meeting, tz_name)
    io_manager.show_summary(records)
    return records
