# tests/test_polling.py
import asyncio
import httpx
import pytest
from social_media_automations import Bot
from social_media_automations.errors import ApiError, AuthError


def upd(uid, text="hi"):
    return {"update_id": uid, "type": "message",
            "channel": {"id": "ch", "ig_user_id": "178", "username": "s"},
            "from": {"id": "u", "username": "x"}, "message": {"id": f"m{uid}", "text": text}, "timestamp": 1}


class FakeClient:
    def __init__(self, batches):
        self.batches = list(batches)      # list of (result-or-exception)
        self.calls = []                   # offsets requested
        self.closed = False
    async def get_updates(self, offset, limit, timeout, channel_id):
        self.calls.append(offset)
        if not self.batches:
            return []
        item = self.batches.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    async def aclose(self):
        self.closed = True


async def test_poll_once_dispatches_and_advances_offset():
    bot = Bot("ak_x")
    bot.client = FakeClient([[upd(5, "a"), upd(6, "b")]])
    seen = []

    @bot.on_message()
    async def h(msg, ctx): seen.append(msg.text)

    new_offset = await bot._poll_once(0)
    assert seen == ["a", "b"]
    assert new_offset == 7  # last update_id + 1


async def _noop_sleep(*_a, **_k):
    return None


async def test_run_polling_acks_then_stops(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    bot = Bot("ak_x")
    fake = FakeClient([[upd(1)], [upd(2)]])
    bot.client = fake
    got = []

    @bot.on_message()
    async def h(msg, ctx):
        got.append(msg.text)
        if msg.raw["update_id"] == 2:
            bot.stop()

    await bot._run_polling()
    assert fake.calls[0] == 0          # first poll from offset 0
    assert 2 in fake.calls or 3 in fake.calls  # acked past update 1
    assert fake.closed is True         # client closed on exit


async def test_auth_error_stops_loop(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    bot = Bot("ak_x")
    bot.client = FakeClient([AuthError(401, "bad")])
    await bot._run_polling()  # returns (does not raise)
    assert bot.client.closed is True


async def test_5xx_backs_off_then_continues(monkeypatch):
    sleeps = []
    async def fake_sleep(s): sleeps.append(s)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    bot = Bot("ak_x")
    fake = FakeClient([ApiError(503, "down"), [upd(1)]])
    bot.client = fake

    @bot.on_message()
    async def h(msg, ctx): bot.stop()

    await bot._run_polling()
    assert sleeps and sleeps[0] == 1   # backed off ~1s after the 503


class HangingClient:
    """Simulates a getUpdates long-poll that never returns on its own — only
    cancellation (stop()) can interrupt it."""
    def __init__(self):
        self.closed = False
        self.entered = asyncio.Event()
    async def get_updates(self, offset, limit, timeout, channel_id):
        self.entered.set()
        await asyncio.Event().wait()   # hang until cancelled
    async def aclose(self):
        self.closed = True


async def test_stop_cancels_inflight_long_poll_immediately():
    bot = Bot("ak_x")
    fake = HangingClient()
    bot.client = fake
    task = asyncio.ensure_future(bot._run_polling())
    await fake.entered.wait()                       # we are now blocked in the long-poll
    bot.stop()                                      # like a SIGINT arriving mid-poll
    await asyncio.wait_for(task, timeout=1.0)       # must return promptly, not hang
    assert fake.closed is True                      # client closed cleanly on exit


async def test_logs_polling_started_banner(caplog):
    import logging
    bot = Bot("ak_live_cb3e53773460ccade")
    bot.client = FakeClient([[upd(1)]])

    @bot.on_message()
    async def h(msg, ctx): bot.stop()

    with caplog.at_level(logging.INFO, logger="social_media_automations"):
        await bot._run_polling()
    assert "polling started" in caplog.text
    assert "ak_live_cb3e…" in caplog.text          # masked key shown, full key hidden
