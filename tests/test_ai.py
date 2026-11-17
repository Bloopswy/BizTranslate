import json
import unittest
from unittest import mock

import requests

from meeting_translator.ai_layer import AIManager, GeminiClient, PromptBuilder, ResponseParser, ResponseValidator
from meeting_translator.exceptions import AIConnectionError, AIResponseError
from tests.fake_ai import FailingClient, ScriptedClient
from tests.helpers import good_ai_dict, saved, utterance


class ParserTests(unittest.TestCase):
    def test_plain_fenced_and_chatty_json(self):
        parser = ResponseParser()
        self.assertEqual(parser.parse('{"a": 1}'), {"a": 1})
        self.assertEqual(parser.parse('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parser.parse('Sure! {"a": 1} Hope that helps'), {"a": 1})

    def test_garbage_raises(self):
        for text in ("", "no json here", "{not json}", "[1, 2]", None, 42):
            with self.assertRaises(AIResponseError, msg=repr(text)):
                ResponseParser().parse(text)


class ValidatorTests(unittest.TestCase):
    def test_valid_response_becomes_analysis(self):
        analysis = ResponseValidator().validate(good_ai_dict(tone="angry", intensity=5))
        self.assertEqual(analysis.tone.value, "angry")
        self.assertEqual(analysis.intensity, 5)

    def test_every_schema_violation_is_rejected(self):
        bad = [
            {"detected_language": "French"}, {"tone": "ecstatic"}, {"language_confidence": 1.5},
            {"translation_confidence": -0.1}, {"tone_confidence": "high"}, {"tone_confidence": True},
            {"intensity": 0}, {"intensity": 6}, {"intensity": 3.5}, {"intensity": True}, {"intensity": "3"},
            {"translation": 5}, {"tone_reason": None},
        ]
        for override in bad:
            with self.assertRaises(AIResponseError, msg=repr(override)):
                ResponseValidator().validate(good_ai_dict(**override))

    def test_missing_field_and_non_dict(self):
        data = good_ai_dict()
        del data["translation"]
        with self.assertRaises(AIResponseError):
            ResponseValidator().validate(data)
        with self.assertRaises(AIResponseError):
            ResponseValidator().validate([])


class PromptTests(unittest.TestCase):
    def test_prompt_contains_sentence_and_context(self):
        builder = PromptBuilder()
        prompt = builder.user_prompt(utterance("Where is it?"), [saved(1, "We ship Monday")])
        self.assertIn("Where is it?", prompt)
        self.assertIn("We ship Monday", prompt)
        self.assertIn("Selamat pagi", prompt)  # earlier translation, as context only

    def test_first_sentence_has_no_context(self):
        self.assertIn("first sentence", PromptBuilder().user_prompt(utterance("Hi")))

    def test_context_is_capped(self):
        context = [saved(i, "s%d" % i) for i in range(1, 11)]
        text = PromptBuilder().format_context(context)
        self.assertEqual(len(text.splitlines()), PromptBuilder.MAX_CONTEXT_SENTENCES)
        self.assertIn("s10", text)

    def test_system_instruction_requests_json_and_target_language(self):
        text = PromptBuilder().system_instruction("Chinese")
        self.assertIn("Simplified Chinese", text)
        self.assertIn("ONE JSON object", text)
        self.assertIn("intensity", text)


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def api_payload(text):
    return {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True}, {"text": text}]}}]}


class GeminiClientTests(unittest.TestCase):
    def client(self, **post_kwargs):
        session = mock.Mock()
        session.post.return_value = post_kwargs.get("response")
        if "error" in post_kwargs:
            session.post.side_effect = post_kwargs["error"]
        return GeminiClient("SECRET-KEY", "model-x", session=session), session

    def test_success_skips_thought_parts_and_sends_key_in_header(self):
        client, session = self.client(response=FakeResponse(200, api_payload("hello")))
        self.assertEqual(client.generate("sys", "user"), "hello")
        kwargs = session.post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "SECRET-KEY")
        self.assertIn("model-x", session.post.call_args.args[0])

    def test_failures_raise_connection_error(self):
        cases = [
            {"error": requests.Timeout("slow")}, {"error": requests.ConnectionError("down")},
            {"response": FakeResponse(500, text="boom")}, {"response": FakeResponse(200, payload=None)},
            {"response": FakeResponse(200, {"candidates": []})}, {"response": FakeResponse(200, api_payload(""))},
        ]
        for case in cases:
            client, _ = self.client(**case)
            with self.assertRaises(AIConnectionError, msg=repr(case)):
                client.generate("s", "u")

    def test_api_key_is_not_exposed(self):
        client, _ = self.client(response=FakeResponse())
        self.assertNotIn("SECRET-KEY", repr(client))
        self.assertFalse(hasattr(client, "api_key"))


class AIManagerTests(unittest.TestCase):
    def manager(self, client, attempts=3):
        sleeps = []
        return AIManager(client, attempts, sleep=sleeps.append), sleeps

    def test_returns_validated_analysis(self):
        manager, _ = self.manager(ScriptedClient(ScriptedClient.json_reply(tone="angry", intensity=5)))
        analysis = manager.analyse(utterance())
        self.assertEqual(analysis.tone.value, "angry")

    def test_retries_malformed_output_then_succeeds(self):
        client = ScriptedClient("not json", ScriptedClient.json_reply(intensity=9), ScriptedClient.json_reply())
        manager, sleeps = self.manager(client)
        self.assertIsNotNone(manager.analyse(utterance()))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(sleeps, [2, 4])  # exponential backoff

    def test_connection_failure_returns_none_after_all_attempts(self):
        manager, sleeps = self.manager(FailingClient())
        self.assertIsNone(manager.analyse(utterance()))
        self.assertEqual(len(sleeps), 2)

    def test_recovers_after_transient_connection_error(self):
        client = ScriptedClient(AIConnectionError("timeout"), ScriptedClient.json_reply())
        manager, _ = self.manager(client)
        self.assertIsNotNone(manager.analyse(utterance()))

    def test_context_reaches_the_prompt(self):
        client = ScriptedClient(ScriptedClient.json_reply())
        manager, _ = self.manager(client)
        manager.analyse(utterance("Next one"), [saved(1, "Earlier sentence")])
        self.assertIn("Earlier sentence", client.calls[0][1])
        self.assertIn("Indonesian", client.calls[0][0])  # translate into the listener's language


if __name__ == "__main__":
    unittest.main()
