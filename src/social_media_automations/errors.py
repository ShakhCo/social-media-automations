# src/social_media_automations/errors.py
from __future__ import annotations

import re

_HTML_RE = re.compile(r"<\s*(?:!doctype|html)\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def summarize_body(body: str, limit: int = 200) -> str:
    """Collapse an error response body into a short, single line.

    HTML error pages (e.g. a Cloudflare ``502 Bad gateway``) are reduced to their
    ``<title>`` — or just ``<html error page>`` — so we never dump a whole page of
    markup into the logs. Plain bodies are whitespace-collapsed and truncated.
    """
    text = (body or "").strip()
    if not text:
        return ""
    if _HTML_RE.search(text[:512]):
        m = _TITLE_RE.search(text)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
            if title:
                return title
        return "<html error page>"
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SdkError(Exception):
    """Base class for all SDK errors."""


class ApiError(SdkError):
    """A non-2xx response from the Bot API."""

    def __init__(self, status: int, body: str) -> None:
        summary = summarize_body(body)
        super().__init__(f"HTTP {status}" + (f": {summary}" if summary else ""))
        self.status = status
        self.body = body  # full, untruncated body kept for programmatic inspection


class AuthError(ApiError):
    """A 401 from the Bot API (bad/blocked Account Key)."""
