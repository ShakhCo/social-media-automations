import pytest
from social_media_automations.context import Context
from social_media_automations.models import Update


class FakeClient:
    def __init__(self):
        self.sent = []
        self.comments = []
    async def send_message(self, channel_id, to, text):
        self.sent.append((channel_id, to, text))
    async def reply_comment(self, channel_id, comment_id, text):
        self.comments.append((channel_id, comment_id, text))


class FakeBot:
    def __init__(self):
        self.client = FakeClient()


MSG = {"update_id": 1, "type": "message", "channel": {"id": "ch-1", "ig_user_id": "178", "username": "s"},
       "from": {"id": "igsid-9", "username": "shopper"}, "message": {"id": "m1", "text": "hi"}, "timestamp": 1}
CMT = {"update_id": 2, "type": "comment", "channel": {"id": "ch-1", "ig_user_id": "178", "username": "s"},
       "from": {"id": "u1", "username": None}, "comment": {"id": "c-77", "text": "price?", "media_id": None}, "timestamp": 1}


async def test_reply_dms_the_sender_on_the_update_channel():
    bot = FakeBot()
    ctx = Context(bot, Update.from_dict(MSG))
    await ctx.reply("yo")
    assert bot.client.sent == [("ch-1", "igsid-9", "yo")]


async def test_send_targets_arbitrary_igsid():
    bot = FakeBot()
    ctx = Context(bot, Update.from_dict(MSG))
    await ctx.send("other", "hey")
    assert bot.client.sent == [("ch-1", "other", "hey")]


async def test_reply_comment_uses_comment_id():
    bot = FakeBot()
    ctx = Context(bot, Update.from_dict(CMT))
    await ctx.reply_comment("thanks")
    assert bot.client.comments == [("ch-1", "c-77", "thanks")]


async def test_reply_comment_outside_comment_raises():
    bot = FakeBot()
    ctx = Context(bot, Update.from_dict(MSG))
    with pytest.raises(RuntimeError):
        await ctx.reply_comment("nope")
