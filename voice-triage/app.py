"""Streamlit entry point.   Run with:  streamlit run app.py

Same four layers as the terminal app:

    user / file -> io_manager -> ai_manager -> logic_manager -> data_manager

Every Streamlit widget call lives in io_manager (the user boundary). This file only
wires the layers together, reusing main.process_record for the pipeline itself.
"""

import os

import ai_manager
import data_manager
import io_manager
import main


def run_pipeline(raw_records, records, api_key):
    """Send each submitted record through AI -> logic -> data, with a progress bar.

    Returns (updated_records, counts).
    """
    counts = {"processed": 0, "skipped": 0, "failed": 0}
    bar = io_manager.ui_progress_start("Starting...")
    total = len(raw_records)
    for position, raw_record in enumerate(raw_records, start=1):
        io_manager.ui_progress_update(bar, (position - 1) / total, "Analysing message %d of %d..." % (position, total))
        records, status = main.process_record(raw_record, records, api_key)
        counts[status] += 1
        if status == "processed":
            data_manager.save_records(records)
    io_manager.ui_progress_clear(bar)
    return records, counts


def run_app():
    io_manager.load_env_file()
    io_manager.ui_configure_page()
    main.setup_logging()
    io_manager.ui_header()

    records = data_manager.load_records()
    api_key = io_manager.ui_sidebar(
        os.environ.get("GEMINI_API_KEY", "").strip(), ai_manager.get_model_name(), len(records),
        io_manager.WHISPER_MODEL_NAME,
    )

    submitted = io_manager.ui_input_tabs()
    if submitted:
        if not api_key:
            io_manager.ui_message("error", "Add your Gemini API key in the sidebar first.")
        else:
            records, counts = run_pipeline(submitted, records, api_key)
            io_manager.ui_run_summary(counts)

    io_manager.ui_subheader("Results")
    io_manager.ui_overview(records)
    if records:
        criteria = io_manager.ui_filter_controls()
        io_manager.ui_record_cards(data_manager.filter_records(records, **criteria))
        io_manager.ui_downloads(records)


run_app()
