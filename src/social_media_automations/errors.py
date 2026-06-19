# src/social_media_automations/errors.py
from __future__ import annotations


class SdkError(Exception):
    """Base class for all SDK errors."""


class ApiError(SdkError):
    """A non-2xx response from the Bot API."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"API error {status}: {body}")
        self.status = status
        self.body = body


class AuthError(ApiError):
    """A 401 from the Bot API (bad/blocked Account Key)."""
