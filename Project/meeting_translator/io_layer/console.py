"""The only place that touches print() and input()."""

from __future__ import annotations

from typing import Callable, Iterable, Optional


class Console:
    """Terminal input/output. The functions are injectable so tests can script a conversation."""

    def __init__(self, input_fn: Callable[[str], str] = input, output_fn: Callable[[str], None] = print):
        self._input = input_fn
        self._output = output_fn

    def show(self, text: str) -> None:
        self._output(text)

    def show_error(self, text: str) -> None:
        self._output("Error: " + text)

    def ask(self, prompt: str) -> Optional[str]:
        """One line of input, stripped. End-of-input (no terminal attached) acts like 'quit' -> None."""
        try:
            return self._input(prompt).strip()
        except EOFError:
            return None

    def ask_choice(self, prompt: str, valid_choices: Iterable[str]) -> Optional[str]:
        """Re-prompt until the answer is one of `valid_choices`. None means input ended."""
        valid = list(valid_choices)
        while True:
            answer = self.ask(prompt)
            if answer is None:
                return None
            if answer in valid:
                return answer
            self.show_error("please enter one of: " + ", ".join(c if c else "(just press Enter)" for c in valid))
