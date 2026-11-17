"""Application-specific exceptions.

A small hierarchy lets each layer raise a precise error while callers can still catch
`AppError` to handle "anything that went wrong inside the application".
"""


class AppError(Exception):
    """Base class of every error raised on purpose by this application."""


class ValidationError(AppError):
    """User or file input that does not satisfy the domain rules."""


class RecordFormatError(AppError):
    """A stored record is missing fields or has values of the wrong type."""


class AIError(AppError):
    """Base class of every problem while talking to the AI."""


class AIConnectionError(AIError):
    """Network failure, timeout or a non-200 HTTP answer from the AI service."""


class AIResponseError(AIError):
    """The AI answered, but the answer is malformed or breaks the response schema."""


class SpeechError(AppError):
    """Base class of every problem while turning a recording into text."""


class SpeechUnavailableError(SpeechError):
    """Speech-to-text cannot run at all: the library is not installed or the model cannot be loaded."""


class TranscriptionError(SpeechError):
    """One recording could not be transcribed (empty, too large, unreadable audio...)."""
