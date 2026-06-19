import pytest
from social_media_automations.filters import make_text_filter


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
