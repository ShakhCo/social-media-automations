# tests/test_errors.py
from social_media_automations.errors import SdkError, ApiError, AuthError, summarize_body


CLOUDFLARE_502 = """<!DOCTYPE html>
<html class="no-js" lang="en-US">
<head>
<title>automations.uz | 502: Bad gateway</title>
<link rel="stylesheet" href="/cdn-cgi/styles/main.css" />
</head>
<body><h1>Bad gateway</h1><p>Error code 502</p></body>
</html>"""


def test_api_error_carries_status_and_body():
    e = ApiError(500, "boom")
    assert e.status == 500
    assert e.body == "boom"
    assert isinstance(e, SdkError)


def test_auth_error_is_an_api_error_with_401():
    e = AuthError(401, "bad key")
    assert isinstance(e, ApiError)
    assert e.status == 401


def test_api_error_message_is_concise_for_html_pages():
    e = ApiError(502, CLOUDFLARE_502)
    msg = str(e)
    # Single, short line — no raw HTML markup leaking into logs.
    assert "\n" not in msg
    assert "<" not in msg and "DOCTYPE" not in msg
    assert msg == "HTTP 502: automations.uz | 502: Bad gateway"
    # ...but the full body stays available for programmatic inspection.
    assert e.body == CLOUDFLARE_502


def test_summarize_body_extracts_title():
    assert summarize_body(CLOUDFLARE_502) == "automations.uz | 502: Bad gateway"


def test_summarize_body_falls_back_for_titleless_html():
    assert summarize_body("<html><body>nope</body></html>") == "<html error page>"


def test_summarize_body_collapses_and_truncates_plain_text():
    assert summarize_body("  too    many   spaces ") == "too many spaces"
    long = "x" * 500
    out = summarize_body(long, limit=200)
    assert len(out) == 200 and out.endswith("…")


def test_summarize_body_handles_empty():
    assert summarize_body("") == ""
    assert str(ApiError(500, "")) == "HTTP 500"
