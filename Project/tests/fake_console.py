"""A Console fed from a list of answers, collecting everything shown."""

from meeting_translator.io_layer import Console


class ScriptedConsole(Console):
    def __init__(self, *answers):
        self.answers = list(answers)
        self.shown = []
        super().__init__(self._input, self.shown.append)

    def _input(self, prompt):
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)
