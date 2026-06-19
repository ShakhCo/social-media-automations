import pytest
from social_media_automations.filters import make_text_filter, make_payload_filter


def test_no_args_matches_everything():
    f = make_text_filter(None, None)
    assert f("anything") is True
    assert f("") is True


def test_text_is_case_insensitive_substring():
    f = make_text_filter("price", None)
    assert f("what is the PRICE?") is True
    assert f("cost") is False


def test_regex_uses_search():
    f = make_text_filter(None, r"\bbook\b")
    assert f("i want to book now") is True
    assert f("textbook") is False


def test_both_args_raises():
    with pytest.raises(ValueError):
        make_text_filter("a", "b")


def test_payload_no_args_matches_everything():
    f = make_payload_filter(None, None)
    assert f("book") is True
    assert f("") is True


def test_payload_matches_exactly_not_substring():
    f = make_payload_filter("book", None)
    assert f("book") is True
    assert f("bookmark_delete") is False  # exact, not substring
    assert f("BOOK") is False             # exact, case-sensitive


def test_payload_regex_uses_search():
    f = make_payload_filter(None, r"^svc_\d+$")
    assert f("svc_123") is True
    assert f("svc_x") is False


def test_payload_both_args_raises():
    with pytest.raises(ValueError):
        make_payload_filter("a", "b")
