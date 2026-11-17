"""Shared test helpers: fake records, fake AI fields and the Streamlit stub.

Functions here must NOT start with test_ (the runner would treat them as tests)."""

from unittest import mock

import data_manager
import io_manager
import logic_manager


def make_setup():
    return io_manager.normalise_setup({
        "meeting": "m1",
        "parties": {"A": {"name": "Acme", "language": "English"}, "B": {"name": "Mitra", "language": "Indonesian"}},
    })


def good_ai(**overrides):
    fields = {
        "detected_language": "English", "language_confidence": 0.95,
        "translation": "Selamat pagi", "translation_confidence": 0.9,
        "tone": "neutral", "tone_confidence": 0.9, "intensity": 2,
        "tone_reason": "Tenang.",
    }
    fields.update(overrides)
    return fields


def utterance(text="Good morning", speaker="A", timestamp="2026-10-14T09:00:00+00:00", position="", setup=None):
    record, problem = io_manager.make_utterance(setup or make_setup(), speaker, text, timestamp, "text", position)
    assert problem is None, problem
    return record


def saved(seq, text="hi", meeting="m1", speaker="A", **extra):
    """A fully processed record, as stored in records.json."""
    record = {**utterance(text, speaker, "2026-10-14T09:%02d:00+00:00" % seq, position=seq), **good_ai(), "seq": seq,
              "outcome": "ACCEPT", "reasons": ["clear and routine"]}
    record["meeting"] = meeting
    record.update(extra)
    return record


def ids(records):
    return [r["id"] for r in records]


def filter_sample():
    return [
        saved(1, "a", speaker="A", tone="angry", detected_language="English", target_language="Indonesian", outcome="TENSION"),
        saved(2, "b", speaker="B", tone="happy", detected_language="Chinese", target_language="English", outcome="ACCEPT"),
        saved(3, "c", speaker="B", tone="angry", detected_language="Chinese", target_language="English", outcome="CHECK"),
        saved(4, "d", speaker="A", tone="neutral", detected_language="Indonesian", target_language="Chinese", outcome="ACCEPT",
              meeting="m2"),
    ]


def make_streamlit_stub(session_state=None):
    def make_column():
        column = mock.MagicMock()
        column.selectbox.return_value = "All"
        column.multiselect.return_value = []
        return column

    stub = mock.MagicMock()
    stub.columns.side_effect = lambda spec: [make_column() for _ in range(spec if isinstance(spec, int) else len(spec))]
    stub.tabs.side_effect = lambda names: [mock.MagicMock() for _ in names]
    stub.selectbox.return_value = "All"
    stub.text_input.return_value = ""
    stub.session_state = {} if session_state is None else session_state
    return stub


def stub_modules(stub):
    return {"streamlit": stub, "streamlit.components": stub.components,
            "streamlit.components.v1": stub.components.v1, "pandas": mock.MagicMock()}


def answer(stub, selectbox=None, text_input=None):
    """Make selectbox / text_input return chosen values per widget key."""
    selectbox, text_input = selectbox or {}, text_input or {}
    stub.selectbox.side_effect = lambda label, options=None, **kw: selectbox.get(kw.get("key"), "All")
    stub.text_input.side_effect = lambda label, **kw: text_input.get(kw.get("key"), "")


def clicking(stub, *clicked):
    """Buttons named in `clicked` return True; like Streamlit, a click runs its on_click callback first."""
    def button(label, **kw):
        if kw.get("key") in clicked:
            if kw.get("on_click"):
                kw["on_click"](*kw.get("args", ()))
            return True
        return False
    stub.button.side_effect = button

def merged(record=None, **ai_overrides):
    """A sentence record merged with AI fields, as logic_manager receives it."""
    return {**(record or utterance()), **good_ai(**ai_overrides)}


def decide(record, ai_fields):
    """Run logic_manager.route on a sentence plus AI fields."""
    return logic_manager.route({**record, **ai_fields})


def with_terminal(function, *args, typed=()):
    """Call `function` with scripted keyboard input. Returns (result, printed_lines).
    When the scripted input runs out the program sees end-of-input, like a closed terminal."""
    remaining = iter(typed)

    def fake_input(prompt=""):
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError

    printed = []
    with mock.patch("builtins.input", fake_input), \
            mock.patch("builtins.print", lambda *a, **k: printed.append(" ".join(str(x) for x in a))):
        result = function(*args)
    return result, printed
