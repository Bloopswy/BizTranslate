"""Tests for io_manager: terminal prompts, input validators, .env loading, the CLI menu loop."""

import json
import os
import tempfile
from unittest import mock

import ai_manager
import data_manager
import io_manager
import main

from helpers import (make_setup, good_ai, with_terminal)


def test_load_env_file_parses_and_respects_existing_values():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, ".env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# comment\nTEST_KEY_A=abc\nexport TEST_KEY_B=\"quoted value\"\nTEST_KEY_C=keep\n\nbadline\n")
        os.environ["TEST_KEY_C"] = "already-set"
        try:
            assert io_manager.load_env_file(path) == 2
            assert os.environ["TEST_KEY_A"] == "abc" and os.environ["TEST_KEY_B"] == "quoted value"
            assert os.environ["TEST_KEY_C"] == "already-set"
            assert io_manager.load_env_file(os.path.join(folder, "missing.env")) == 0
        finally:
            for name in ("TEST_KEY_A", "TEST_KEY_B", "TEST_KEY_C"):
                os.environ.pop(name, None)


def test_terminal_menu_flow_setup_then_say_a_sentence():
    typed = iter(["7", "board", "Budi", "2", "Li", "3",   # setup: Budi speaks Indonesian, Li speaks Chinese
                  "1", "1", "Selamat pagi semuanya",       # speaker 1 says a sentence
                  "3", "8"])                                # show panel, quit
    output, seen = [], []

    def fake_analyse(record, api_key, context=None, model=None):
        seen.append(record)
        return good_ai(detected_language="Indonesian", translation="\u5927\u5BB6\u65E9\u4E0A\u597D")

    with mock.patch("builtins.input", lambda prompt="": next(typed)), \
            mock.patch("builtins.print", lambda *args, **kw: output.append(" ".join(str(a) for a in args))), \
            mock.patch.object(ai_manager, "analyse_record", fake_analyse), \
            mock.patch.object(data_manager, "save_records", return_value=True):
        records = main.run_interactive([], "key", make_setup(), "UTC")
    assert len(records) == 1 and seen[0]["meeting"] == "board"
    assert (seen[0]["speaker_name"], seen[0]["speaker_language"], seen[0]["target_language"]) == ("Budi", "Indonesian", "Chinese")
    text = "\n".join(output)
    assert "Latest translation" in text and "\u5927\u5BB6\u65E9\u4E0A\u597D" in text and "Previous" not in text.split("Latest")[0]
    assert "no earlier sentences" in text


def test_prompt_choice_reprompts_until_valid_and_handles_end_of_input():
    result, printed = with_terminal(io_manager.prompt_choice, "Pick: ", ["1", "2"], typed=["x", "9", "2"])
    assert result == "2" and sum("please enter one of" in line for line in printed) == 2
    result, _ = with_terminal(io_manager.prompt_choice, "Pick: ", ["1", "2"], typed=["x"])
    assert result is None, "closed terminal means 'quit', not a crash"


def test_prompt_sentence_rejects_empty_and_too_long_text():
    result, printed = with_terminal(io_manager.prompt_sentence, typed=["", "x" * 3000, "Good morning"])
    assert result == "Good morning" and len(printed) == 2
    assert with_terminal(io_manager.prompt_sentence, typed=[])[0] is None


def test_clean_label_and_valid_timestamp():
    assert io_manager.clean_label("  Acme \n\t Foods  ", "fallback", 40) == "Acme Foods"
    assert io_manager.clean_label("abcdefghij", "fallback", 5) == "abcde"
    assert io_manager.clean_label(None, "fallback", 5) == "fallback" and io_manager.clean_label("  ", "fb", 5) == "fb"
    assert io_manager.valid_timestamp(" 2026-10-14T09:00:05+08:00 ") == "2026-10-14T09:00:05+08:00"
    assert io_manager.valid_timestamp("yesterday") == "" and io_manager.valid_timestamp(None) == ""


def test_prompt_filter_returns_arguments_for_the_filter_function():
    setup = make_setup()
    assert with_terminal(io_manager.prompt_filter, setup, typed=["1", "angry"])[0] == {"tones": ["angry"]}
    assert with_terminal(io_manager.prompt_filter, setup, typed=["2", "Chinese"])[0] == {"languages": ["Chinese"]}
    assert with_terminal(io_manager.prompt_filter, setup, typed=["3", "English"])[0] == {"target_languages": ["English"]}
    assert with_terminal(io_manager.prompt_filter, setup, typed=["4", "2"])[0] == {"speakers": ["Mitra"]}
    assert with_terminal(io_manager.prompt_filter, setup, typed=["5", "CHECK"])[0] == {"outcome": "CHECK"}
    assert with_terminal(io_manager.prompt_filter, setup, typed=[])[0] is None


def test_prompt_file_choice_and_prompt_speaker():
    files = ["a.json", "b.txt"]
    assert with_terminal(io_manager.prompt_file_choice, files, typed=["A"])[0] == files
    assert with_terminal(io_manager.prompt_file_choice, files, typed=["2"])[0] == ["b.txt"]
    result, printed = with_terminal(io_manager.prompt_file_choice, [], typed=[])
    assert result is None and any("no .json or .txt files" in line for line in printed)
    assert with_terminal(io_manager.prompt_speaker, make_setup(), typed=["2"])[0] == "B"


def test_prompt_setup_keeps_values_when_enter_is_pressed():
    current = make_setup()
    same, _ = with_terminal(io_manager.prompt_setup, current, typed=["", "", "", "", ""])
    assert same == current
    changed, _ = with_terminal(io_manager.prompt_setup, current, typed=["board", "Budi", "2", "", "3"])
    assert changed["meeting"] == "board" and changed["parties"]["A"] == {"name": "Budi", "language": "Indonesian"}
    assert changed["parties"]["B"] == {"name": "Mitra", "language": "Chinese"}
    assert with_terminal(io_manager.prompt_setup, current, typed=["board"])[0] is None
