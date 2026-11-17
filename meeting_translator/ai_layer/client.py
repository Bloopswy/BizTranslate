"""Transport to the AI service, behind an interface so the rest of the app never knows
which provider (or fake) it is talking to."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

from ..exceptions import AIConnectionError


class AIClient(ABC):
    """Interface: send a system instruction and a user prompt, get the model's raw text back."""

    @abstractmethod
    def generate(self, system_instruction: str, user_prompt: str) -> str:
        """Return the model's text. Raise AIConnectionError if the service cannot be reached
        or answers with an error."""


class GeminiClient(AIClient):
    """Google AI Studio / Gemini API client (serves the Gemma models)."""

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 60, session=None):
        self.__api_key = api_key  # name-mangled: never printed, logged or exposed
        self._model = model
        self._timeout = timeout_seconds
        self._session = session if session is not None else requests

    @property
    def model(self) -> str:
        return self._model

    def __repr__(self) -> str:
        return "GeminiClient(model=%r)" % self._model  # deliberately omits the key

    def _build_body(self, system_instruction: str, user_prompt: str) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0,  # keeps output as repeatable as the API allows
                "thinkingConfig": {"thinkingLevel": "minimal"},  # fast, no reasoning text
            },
        }

    def generate(self, system_instruction: str, user_prompt: str) -> str:
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.__api_key}
        try:
            response = self._session.post(
                self.API_URL.format(model=self._model), headers=headers,
                json=self._build_body(system_instruction, user_prompt), timeout=self._timeout)
        except requests.RequestException as error:
            raise AIConnectionError("API request failed: %s" % error)
        if response.status_code != 200:
            logging.warning("API returned HTTP %s: %s", response.status_code, response.text[:300])
            raise AIConnectionError("API returned HTTP %s" % response.status_code)
        try:
            parts = response.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise AIConnectionError("unexpected API response shape: %s" % error)
        if not text:
            raise AIConnectionError("API returned no text")
        return text
