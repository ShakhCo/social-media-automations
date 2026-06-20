# tests/test_channel_filter.py
from social_media_automations import Bot


def _ids(**kw):
    bot = Bot("ak_x", **kw)
    return bot._channel_ids


def test_channel_ids_list_is_stored():
    assert _ids(channel_ids=["a", "b"]) == ["a", "b"]


def test_singular_channel_id_is_wrapped():
    assert _ids(channel_id="c") == ["c"]


def test_both_are_unioned():
    assert _ids(channel_ids=["a"], channel_id="c") == ["a", "c"]


def test_neither_is_none():
    assert _ids() is None
