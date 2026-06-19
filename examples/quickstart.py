"""Minimal Instagram bot using the social-media-automations SDK.

Run:  SMA_KEY=ak_your_key python examples/quickstart.py
First flip your channel to bot mode (once), then this bot answers DMs + comments.
"""
import os

from social_media_automations import Bot

app = Bot(account_key=os.environ["SMA_KEY"])


@app.on_message(text="price")
async def price(msg, ctx):
    await ctx.reply("Solo: $6/mo. Team: $4/member/mo.")


@app.on_message()
async def greet(msg, ctx):
    name = msg.from_user.username or "friend"
    await ctx.reply(f"Hi {name}! How can I help?")


@app.on_comment()
async def thank(comment, ctx):
    await ctx.reply_comment("Thanks! 🙌")


@app.on_postback()
async def button(pb, ctx):
    if pb.payload == "book":
        await ctx.reply("Let's get you booked!")


if __name__ == "__main__":
    app.run_polling()
