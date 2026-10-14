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
import logic_manager
import main


def run_pipeline(raw_records, records, api_key):
    """Send each submitted sentence through AI -> logic -> data, with a progress bar.

    Returns (updated_records, counts).
    """
    counts = {"processed": 0, "skipped": 0, "failed": 0}
    bar = io_manager.ui_progress_start("Starting...")
    total = len(raw_records)
    for position, raw_record in enumerate(raw_records, start=1):
        io_manager.ui_progress_update(bar, (position - 1) / total, "Translating sentence %d of %d..." % (position, total))
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
    api_key, setup, tz_name = io_manager.ui_sidebar(
        os.environ.get("GEMINI_API_KEY", "").strip(), ai_manager.get_model_name(), io_manager.WHISPER_MODEL_NAME
    )
    context_count = logic_manager.CONTEXT_SENTENCES
    live_tab, transcript_tab, filter_tab = io_manager.ui_main_tabs()

    with live_tab:
        submitted = io_manager.ui_live_input(setup)
        if submitted:
            if not api_key:
                io_manager.ui_message("error", "Add your API key in the sidebar first.")
            else:
                records, counts = run_pipeline(submitted, records, api_key)
                io_manager.ui_run_summary(counts)
        latest, previous = data_manager.latest_with_context(records, setup["meeting"], context_count)
        io_manager.ui_conversation_panel(latest, previous, tz_name, context_count)

    with transcript_tab:
        meeting = io_manager.ui_meeting_picker(data_manager.list_meetings(records), setup["meeting"])
        rows = data_manager.meeting_records(records, meeting)
        io_manager.ui_overview(rows)
        io_manager.ui_transcript(rows, tz_name)
        io_manager.ui_downloads(rows, tz_name, key_prefix="meeting", file_stem=io_manager.safe_filename(meeting))

    with filter_tab:
        if not records:
            io_manager.ui_message("info", "Nothing to filter yet. Translate a sentence in the Live tab first.")
        else:
            criteria = io_manager.ui_filter_tab(records)
            matched = data_manager.filter_records_multi(records, **criteria)
            io_manager.ui_filter_results(matched, len(records), tz_name)


run_app()
