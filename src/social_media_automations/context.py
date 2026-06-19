from __future__ import annotations

from .models import Update


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
