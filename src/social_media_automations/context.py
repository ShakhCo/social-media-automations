from __future__ import annotations

import asyncio
import logging

from .models import Update

logger = logging.getLogger("social_media_automations")


class Context:
    def __init__(self, bot, update: Update) -> None:
        self.bot = bot
        self.update = update

    async def reply(self, text: str) -> None:
        u = self.update
        await self.bot.client.send_message(channel_id=u.channel.id, to=u.from_user.id, text=text)

    async def send(self, to: str, text: str) -> None:
        await self.bot.client.send_message(channel_id=self.update.channel.id, to=to, text=text)

    async def reply_comment(self, text: str) -> None:
        u = self.update
        if u.comment is None:
            raise RuntimeError("reply_comment() is only valid inside an on_comment handler")
        await self.bot.client.reply_comment(channel_id=u.channel.id, comment_id=u.comment.id, text=text)

    async def typing(self, seconds: float = 1.0) -> None:
        """Show Instagram's "typing…" indicator for the current DM, then pause briefly
        so it's visible before your reply. Best-effort: a failure (closed messaging
        window, network, non-DM context) is logged and swallowed — it never breaks the
        bot, and the following reply still runs."""
        u = self.update
        try:
            await self.bot.client.send_action(
                channel_id=u.channel.id, to=u.from_user.id, action="typing_on"
            )
        except Exception:
            logger.debug("typing indicator failed for update %s", u.update_id, exc_info=True)
            return
        await asyncio.sleep(seconds)
