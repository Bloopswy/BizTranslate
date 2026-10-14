"""Plain-function test runner (no classes, per the 100% procedural constraint).

    python tests/run_tests.py                    run every tests/test_*.py file
    python tests/run_tests.py test_ai_response   run only files whose name contains the text

No network, API key, Streamlit or Whisper install needed: those are replaced with fakes.
Shared fakes live in tests/helpers.py.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                        # tests/helpers.py
sys.path.insert(0, os.path.join(HERE, ".."))    # the managers

import io_manager


def discover(filters):
    """All (label, function) pairs from the test_*.py files that match the optional filters."""
    names = sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
    tests = []
    for name in names:
        if filters and not any(text in name for text in filters):
            continue
        module = importlib.import_module(name)
        for attribute in sorted(dir(module)):
            function = getattr(module, attribute)
            if attribute.startswith("test_") and callable(function) and function.__module__ == name:
                tests.append(("%s::%s" % (name, attribute), function))
    return tests


def run_all(filters=()):
    tests = discover(filters)
    failures = 0
    for label, function in tests:
        try:
            function()
            io_manager.show_message("PASS  " + label)
        except AssertionError as error:
            failures += 1
            io_manager.show_message("FAIL  %s %s" % (label, error))
        except Exception as error:  # noqa: BLE001 - report any crash as a failure
            failures += 1
            io_manager.show_message("ERROR %s: %r" % (label, error))
    io_manager.show_message("\n%d tests, %d failed" % (len(tests), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_all(sys.argv[1:]))
