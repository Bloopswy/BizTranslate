"""Entry point. Wires the four layers together:

    user / file -> io_manager -> ai_manager -> logic_manager -> data_manager

Usage:
    python main.py            interactive menu
    python main.py --batch    process every file in the input folder, print a summary, exit
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
    """Run one input record through AI -> logic -> data.

    Returns (updated_records, status) where status is 'processed', 'skipped' or 'failed'.
    """
    if data_manager.find_by_id(records, raw_record["id"]) is not None:
        return records, "skipped"  # already processed in an earlier run

    ai_fields = ai_manager.analyse_record(raw_record, api_key)
    if ai_fields is None:
        return records, "failed"  # logged by ai_manager; retried on the next run

    clean = dict(raw_record)
    clean.setdefault("input_type", "text")

    decision = logic_manager.decide_outcome(clean, ai_fields)
    full_record = {**clean, **ai_fields, **decision}
    return data_manager.add_record(records, full_record), "processed"


def process_records(raw_records, records, api_key):
    """Process many records, saving after each one so progress is never lost."""
    counts = {"processed": 0, "skipped": 0, "failed": 0}
    for raw_record in raw_records:
        records, status = process_record(raw_record, records, api_key)
        counts[status] += 1
        if status == "processed":
            data_manager.save_records(records)
            io_manager.show_message("--- " + raw_record["id"])
            io_manager.show_message(io_manager.format_record(data_manager.find_by_id(records, raw_record["id"])))
        elif status == "failed":
            io_manager.show_error("AI analysis failed for record %s (see log); continuing" % raw_record["id"])
    io_manager.show_message(
        "\nDone: %(processed)d processed, %(skipped)d already done, %(failed)d failed." % counts
    )
    return records


def load_raw_records_from_files(file_names):
    """Read the chosen input files. Returns a de-duplicated list of raw records."""
    raw_records, seen = [], set()
    for name in file_names:
        found, errors = io_manager.read_input_file(os.path.join(io_manager.INPUT_DIR, name))
        for message in errors:
            io_manager.show_error(message)
        for record in found:
            if record["id"] not in seen:
                seen.add(record["id"])
                raw_records.append(record)
    return raw_records


def run_batch(records, api_key):
    files = io_manager.list_input_files()
    if not files:
        io_manager.show_error("no .json or .txt files found in the '%s' folder" % io_manager.INPUT_DIR)
        return records
    raw_records = load_raw_records_from_files(files)
    records = process_records(raw_records, records, api_key)
    io_manager.show_summary(records)
    return records


def run_interactive(records, api_key):
    while True:
        choice = io_manager.prompt_menu()
        if choice is None or choice == "6":
            io_manager.show_message("Goodbye.")
            return records
        if choice == "1":
            chosen = io_manager.prompt_file_choice(io_manager.list_input_files())
            if chosen:
                records = process_records(load_raw_records_from_files(chosen), records, api_key)
        elif choice == "2":
            entry = io_manager.prompt_transcript()
            if entry is not None:
                raw_record, problem = io_manager.normalise_input_record(entry)
                if problem:
                    io_manager.show_error(problem)
                else:
                    records = process_records([raw_record], records, api_key)
        elif choice == "3":
            io_manager.show_records(records)
        elif choice == "4":
            criteria = io_manager.prompt_filter()
            if criteria is not None:
                io_manager.show_records(data_manager.filter_records(records, **criteria))
        elif choice == "5":
            io_manager.show_summary(records)


def main():
    parser = argparse.ArgumentParser(description="Multilingual voice triage")
    parser.add_argument("--batch", action="store_true", help="process the input folder and exit")
    args = parser.parse_args()

    io_manager.load_env_file()
    setup_logging()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        io_manager.show_error(
            "GEMINI_API_KEY is not set. Either create a file named .env in this folder containing\n"
            "  GEMINI_API_KEY=your-key\n"
            "or set it in your terminal first (macOS/Linux: export GEMINI_API_KEY=your-key, "
            "Windows PowerShell: $env:GEMINI_API_KEY=\"your-key\")."
        )
        return 1

    records = data_manager.load_records()
    io_manager.show_message("Loaded %d saved record(s). Model: %s" % (len(records), ai_manager.get_model_name()))

    if args.batch:
        run_batch(records, api_key)
    else:
        run_interactive(records, api_key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
