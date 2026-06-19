# src/social_media_automations/bot.py
from __future__ import annotations

import logging
from typing import Callable, List, Optional, Tuple

from .client import ApiClient, DEFAULT_BASE_URL
from .context import Context
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
