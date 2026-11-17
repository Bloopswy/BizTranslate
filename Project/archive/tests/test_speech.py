"""Tests for io_manager: speech-to-text (Whisper replaced by a fake)."""

import sys
from types import SimpleNamespace
from unittest import mock

import io_manager


def fake_whisper_module(language="en", probs=None, text=" hello there "):
    model = mock.MagicMock()
    info = SimpleNamespace(language=language, all_language_probs=probs)
    model.transcribe.side_effect = lambda *a, **k: (iter([SimpleNamespace(text=text)]), info)
    module = mock.MagicMock()
    module.WhisperModel.return_value = model
    return module, model


def test_transcribe_audio_with_chosen_language():
    module, model = fake_whisper_module()
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": module}):
        text, code, error = io_manager.transcribe_audio(b"wav", "id-ID")
    io_manager._speech_models.clear()
    assert (text, code, error) == ("hello there", "id-ID", None)
    assert model.transcribe.call_count == 1 and model.transcribe.call_args.kwargs["language"] == "id"


def test_transcribe_audio_auto_detect_is_restricted_to_supported_languages():
    module, model = fake_whisper_module(language="ms", probs=[("ms", 0.5), ("id", 0.4), ("en", 0.1)])
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": module}):
        text, code, error = io_manager.transcribe_audio(b"wav", None)
    io_manager._speech_models.clear()
    assert error is None and code == "id-ID"
    assert model.transcribe.call_count == 2 and model.transcribe.call_args.kwargs["language"] == "id"


def test_transcribe_audio_reports_errors_instead_of_crashing():
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": None}):  # simulates "not installed"
        text, code, error = io_manager.transcribe_audio(b"wav", None)
    assert text == "" and code is None and "faster-whisper" in error
    module, model = fake_whisper_module()
    model.transcribe.side_effect = RuntimeError("bad audio")
    io_manager._speech_models.clear()
    with mock.patch.dict(sys.modules, {"faster_whisper": module}):
        text, code, error = io_manager.transcribe_audio(b"wav", "en-US")
    io_manager._speech_models.clear()
    assert text == "" and "bad audio" in error


def test_pick_supported_language():
    assert io_manager.pick_supported_language([("fr", 0.9), ("zh", 0.05), ("en", 0.02)]) == "zh"
    assert io_manager.pick_supported_language([("fr", 0.9)]) is None
    assert io_manager.pick_supported_language(None) is None
