# tests/test_dispatch.py
from social_media_automations import Bot
from social_media_automations.models import Update

MSG = {"update_id": 1, "type": "message", "channel": {"id": "ch", "ig_user_id": "178", "username": "s"},
       "from": {"id": "u", "username": "x"}, "message": {"id": "m", "text": "what PRICE?"}, "timestamp": 1}
CMT = {"update_id": 2, "type": "comment", "channel": {"id": "ch", "ig_user_id": "178", "username": "s"},
       "from": {"id": "u", "username": "x"}, "comment": {"id": "c", "text": "hi", "media_id": None}, "timestamp": 1}


def pb(payload):
    return {"update_id": 3, "type": "postback", "channel": {"id": "ch", "ig_user_id": "178", "username": "s"},
            "from": {"id": "u", "username": "x"}, "postback": {"payload": payload}, "timestamp": 1}


def make_bot(monkeypatch=None):
    return Bot(account_key="ak_x")


async def test_first_match_wins():
    bot = make_bot()
    hits = []

    @bot.on_message(text="price")
    async def a(msg, ctx): hits.append("a")

    @bot.on_message()
    async def b(msg, ctx): hits.append("b")

    ran = await bot.dispatch(Update.from_dict(MSG))
    assert ran is True
    assert hits == ["a"]  # only the first matching handler


async def test_comment_handler_only_gets_comments():
    bot = make_bot()
    seen = []

    @bot.on_comment()
    async def c(cm, ctx): seen.append("c")

    @bot.on_message()
    async def m(msg, ctx): seen.append("m")

    await bot.dispatch(Update.from_dict(CMT))
    assert seen == ["c"]


async def test_no_match_returns_false():
    bot = make_bot()

    @bot.on_message(text="zzz")
    async def a(msg, ctx): ...

    assert await bot.dispatch(Update.from_dict(MSG)) is False


async def test_handler_exception_is_swallowed():
    bot = make_bot()

    @bot.on_message()
    async def boom(msg, ctx): raise ValueError("kaboom")

    # does not raise; counts as matched
    assert await bot.dispatch(Update.from_dict(MSG)) is True


async def test_postback_payload_filter_matches_exactly():
    bot = make_bot()
    hits = []

    @bot.on_postback(payload="book")
    async def book(p, ctx): hits.append("book")

    @bot.on_postback()
    async def anytap(p, ctx): hits.append("any")

    await bot.dispatch(Update.from_dict(pb("book")))
    assert hits == ["book"]                 # exact payload handler wins (first match)

    hits.clear()
    await bot.dispatch(Update.from_dict(pb("cancel")))
    assert hits == ["any"]                  # "book" handler doesn't match "cancel"; falls through


async def test_postback_regex_filter():
    bot = make_bot()
    seen = []

    @bot.on_postback(regex=r"^svc_\d+$")
    async def service(p, ctx): seen.append(p.payload)

    assert await bot.dispatch(Update.from_dict(pb("svc_42"))) is True
    assert await bot.dispatch(Update.from_dict(pb("svc_x"))) is False
    assert seen == ["svc_42"]
