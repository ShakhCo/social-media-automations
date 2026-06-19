# src/social_media_automations/bot.py
from __future__ import annotations

import asyncio
import logging
import signal
from typing import Callable, List, Optional, Tuple

import httpx

from .client import ApiClient, DEFAULT_BASE_URL
from .context import Context
from .errors import ApiError, AuthError
from .filters import make_text_filter
from .models import Update

logger = logging.getLogger("social_media_automations")

Handler = Tuple[str, Callable[[str], bool], Callable]


class Bot:
    def __init__(self, account_key: str, base_url: str = DEFAULT_BASE_URL, *,
                 poll_timeout: int = 25, poll_limit: int = 50, channel_id: Optional[str] = None) -> None:
        self.client = ApiClient(account_key, base_url)
        self._poll_timeout = poll_timeout
        self._poll_limit = poll_limit
        self._channel_id = channel_id
        self._handlers: List[Handler] = []
        self._stop = False

    def on_message(self, text: Optional[str] = None, regex: Optional[str] = None) -> Callable:
        flt = make_text_filter(text, regex)
        def deco(fn: Callable) -> Callable:
            self._handlers.append(("message", flt, fn))
            return fn
        return deco

    def on_comment(self) -> Callable:
        def deco(fn: Callable) -> Callable:
            self._handlers.append(("comment", lambda s: True, fn))
            return fn
        return deco

    def on_postback(self) -> Callable:
        def deco(fn: Callable) -> Callable:
            self._handlers.append(("postback", lambda s: True, fn))
            return fn
        return deco

    def _obj_and_text(self, update: Update):
        if update.type == "message":
            return update.message, update.message.text
        if update.type == "comment":
            return update.comment, update.comment.text
        if update.type == "postback":
            return update.postback, update.postback.payload
        return None, ""

    def stop(self) -> None:
        self._stop = True

    async def _poll_once(self, offset: int) -> int:
        rows = await self.client.get_updates(offset, self._poll_limit, self._poll_timeout, self._channel_id)
        for row in rows:
            uid = row.get("update_id")
            if isinstance(uid, int):
                offset = uid + 1          # advance BEFORE dispatch (crash-safe)
            update = Update.from_dict(row)
            if update is None:
                continue                  # unknown type: already advanced past it
            await self.dispatch(update)
            if self._stop:
                break
        return offset

    async def _run_polling(self) -> None:
        offset = 0
        backoff = 0
        try:
            while not self._stop:
                try:
                    offset = await self._poll_once(offset)
                    backoff = 0
                except AuthError:
                    logger.error("invalid Account Key (401) — stopping")
                    break
                except (httpx.HTTPError, ApiError) as e:
                    status = getattr(e, "status", None)
                    if isinstance(e, ApiError) and status is not None and status < 500:
                        logger.error("client error %s — stopping: %s", status, e)
                        break
                    delay = min(2 ** backoff, 30)
                    backoff += 1
                    logger.warning("transient error (%s); retrying in %ss", e, delay)
                    await asyncio.sleep(delay)
        finally:
            await self.client.aclose()

    def run_polling(self) -> None:
        async def _main() -> None:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, self.stop)
                except NotImplementedError:
                    pass  # e.g. Windows
            await self._run_polling()
        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            pass

    async def dispatch(self, update: Update) -> bool:
        obj, text = self._obj_and_text(update)
        for kind, flt, fn in self._handlers:
            if kind != update.type:
                continue
            if not flt(text):
                continue
            ctx = Context(self, update)
            try:
                await fn(obj, ctx)
            except Exception:  # a handler crash must not kill the bot
                logger.exception("handler error for update %s", update.update_id)
            return True
        return False
