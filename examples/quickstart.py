"""Minimal Instagram bot using the social-media-automations SDK.

Run:  SMA_KEY=ak_your_key python examples/quickstart.py
First flip your channel to bot mode (once), then this bot answers DMs + comments.
"""
import os

from social_media_automations import Bot

app = Bot(account_key=os.environ["SMA_KEY"])


@app.on_message(text="price")
async def price(msg, ctx):
    await ctx.reply("Yakka: 72 000 so'm/oy. Jamoa: 49 500 so'm/a'zo/oy.")


@app.on_message()
async def greet(msg, ctx):
    name = msg.from_user.username or "do'st"
    await ctx.reply(f"Salom, {name}! Nima bilan yordam beray?")


@app.on_comment()
async def thank(comment, ctx):
    await ctx.reply_comment("Rahmat! 🙌")


@app.on_postback()
async def button(pb, ctx):
    if pb.payload == "book":
        await ctx.reply("Keling, band qilamiz!")


if __name__ == "__main__":
    app.run_polling()
