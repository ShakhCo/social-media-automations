# social-media-automations (Python SDK)

Async Python client for the Instagram Bot API — register handlers, call `run_polling()`.

## Install
```bash
pip install social-media-automations
```

For local development from a clone: `pip install -e ".[dev]"`

## Quickstart
```python
from social_media_automations import Bot

app = Bot(account_key="ak_...")   # your Account Key — all bot-mode channels

# ...or scope updates to specific channels (server-side filter):
app = Bot(account_key="ak_...", channel_ids=["ch-1", "ch-2"])

@app.on_message()
async def on_dm(msg, ctx):
    await ctx.reply(f"Hi {msg.from_user.username}!")

@app.on_message(text="price")     # case-insensitive substring; or regex="..."
async def price(msg, ctx):
    await ctx.reply("$6/mo")

@app.on_comment()
async def on_comment(c, ctx):
    await ctx.reply_comment("Thanks!")

@app.on_postback(payload="book")  # exact payload; or regex="..."
async def on_btn(pb, ctx):
    await ctx.reply("Let's get you booked!")

app.run_polling()
```

## Handler reference
- `@app.on_message(text=None, regex=None)` — DMs. `text` = case-insensitive substring; `regex` = `re.search`; pass at most one.
- `@app.on_comment()` — public comments.
- `@app.on_postback(payload=None, regex=None)` — button/ice-breaker taps (`pb.payload`). `payload` = exact match; `regex` = `re.search`; pass at most one.

Handlers are `async def handler(obj, ctx)`. First matching handler wins.

## Context (`ctx`)
- `await ctx.reply(text)` — DM the sender.
- `await ctx.reply_comment(text)` — public reply (comment handlers only).
- `await ctx.send(to, text)` — DM an arbitrary IG-scoped id on this channel.

## Notes
- One channel must be in **bot mode** first (`POST /bot/v1/setDeliveryMode`).
- Polling is at-least-once; `msg.id` / `comment.id` are stable for dedup.
- `Ctrl-C` stops the bot cleanly.
