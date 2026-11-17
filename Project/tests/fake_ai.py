"""Fake AI clients: tests never contact the live API."""

import json
from typing import List

from meeting_translator.ai_layer import AIClient
from meeting_translator.exceptions import AIConnectionError
from tests.helpers import good_ai_dict


class ScriptedClient(AIClient):
    """Fake AI: returns the queued replies in order. An Exception instance in the queue is raised.
    Once the queue is down to one reply, that reply repeats."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: List[tuple] = []

    @staticmethod
    def json_reply(**overrides):
        return json.dumps(good_ai_dict(**overrides))

    def generate(self, system_instruction, user_prompt):
        self.calls.append((system_instruction, user_prompt))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class FailingClient(AIClient):
    """Fake AI that is always unreachable."""

    def generate(self, system_instruction, user_prompt):
        raise AIConnectionError("offline")
