# social-media-automations — Python SDK Design

**Date:** 2026-06-20
**Status:** Approved (design); pending implementation plan
**Repo:** `~/Projects/social-media-automations` (new standalone, local git)
**Package (pip):** `social-media-automations` → `import social_media_automations`

## 1. Goal

A `python-telegram-bot`–style **async** Python SDK that wraps the deployed Bot
API (`/bot/v1/*` on `social-media-api.automations.uz`) so a developer can build
an Instagram bot in ~15 lines: pass their Account Key, register handlers, call
`run_polling()`. No public URL, no raw HTTP.

```python
from social_media_automations import Bot

app = Bot(account_key="ak_...")

@app.on_message()
async def on_dm(msg, ctx):
    await ctx.reply(f"Salom {msg.from_user.username}!")

app.run_polling()
```

## 2. Locked decisions (brainstormed 2026-06-20)

| Decision | Choice |
|---|---|
| Async vs sync | **Async** (asyncio; `async def` handlers, `await ctx.reply`) |
| HTTP client | **httpx** (async) |
| Python floor | **3.9+** (matches local 3.9.6; run examples/tests here) |
| Transport | **Polling only** (`run_polling`); webhook deferred |
| Auth | **Single Account Key** (`ak_…`) via `x-api-key` header |
| Handler dispatch | **Flat registry, first-match wins** (Option A) — one update → at most one handler |
| Comment→DM (`reply_dm`) | **Out of v1** — `/bot/v1` doesn't expose it; Meta-gated |
| Distribution | pip-installable from the repo (`pip install -e .`); **no PyPI publish** in this cycle |

## 3. The Bot API it targets (already deployed)

All endpoints under `/bot/v1`, authenticated by `x-api-key: ak_…`.

| Method | Endpoint | Request | Response |
|---|---|---|---|
| GET | `/bot/v1/getUpdates` | query `offset, limit, timeout, channel_id?` | `{ result: Update[] }` |
| POST | `/bot/v1/sendMessage` | `{ channel_id, to, text }` | `{ ok: true }` |
| POST | `/bot/v1/replyComment` | `{ channel_id, comment_id, text }` | `{ ok: true }` |
| GET | `/bot/v1/getMe` | query `channel_id` | `{ channel_id, ig_user_id, username }` |

**Update JSON contract** (only the sub-object matching `type` is present):
```json
{
  "update_id": 1042,
  "type": "message",
  "channel": { "id": "<uuid>", "ig_user_id": "1784...", "username": "salon_momi" },
  "from": { "id": "<igsid>", "username": "shopper" },
  "message": { "id": "mid-7", "text": "can I book?" },
  "comment": { "id": "comment-77", "text": "price?", "media_id": "media-5" },
  "postback": { "payload": "yes_clicked" },
  "timestamp": 1718800000000
}
```
`update_id` is monotonic per account; `channel.id` is what the SDK passes back on
every send (reply routing). Long-poll: server holds up to `timeout` seconds.

## 4. Package layout

```
~/Projects/social-media-automations/
  pyproject.toml                        # PEP 621; name "social-media-automations"; dep: httpx
  src/social_media_automations/
    __init__.py                         # exports Bot + model classes + errors
    bot.py        # Bot (Application): handler registry + run_polling()
    client.py     # ApiClient: async httpx wrapper over /bot/v1
    models.py     # Update, Message, Comment, Postback, User, Channel (dataclasses)
    context.py    # Context (ctx): reply / reply_comment / send, bound to one update
    filters.py    # text/regex matching
    errors.py     # ApiError, AuthError
  examples/quickstart.py
  tests/                                # pytest + respx (mocked httpx, no network)
  README.md
```

Each file has one responsibility; `bot.py` wires them. Files stay small enough to
hold in context. No cross-imports beyond the obvious (bot → client/models/context).

## 5. Public API surface

```python
from social_media_automations import Bot

app = Bot(account_key="ak_...")          # base_url defaults to the prod gateway

@app.on_message()                        # all DMs
async def on_dm(msg, ctx): ...

@app.on_message(text="price")            # case-insensitive substring
async def price(msg, ctx): ...

@app.on_message(regex=r"\bbook\b")       # re.search on the message text
async def book(msg, ctx): ...

@app.on_comment()
async def on_comment(c, ctx): ...

@app.on_postback()
async def on_btn(pb, ctx): ...

app.run_polling()
```

- **Constructor:** `Bot(account_key: str, base_url: str = DEFAULT_BASE_URL, *, poll_timeout: int = 25, poll_limit: int = 50, channel_id: str | None = None)`.
  `channel_id` set → polling scoped to one channel; unset → all the account's bot-mode channels.
- **Decorators** register `(kind, filter, fn)` in order. Filters: `on_message` accepts
  optional `text=` (case-insensitive substring) **or** `regex=` (passed to `re.search`);
  passing both raises `ValueError`. `on_comment` / `on_postback` take no filter args in v1
  (match in the handler body — see the `payload` example).
- **Handler signature:** `async def handler(obj, ctx)` where `obj` is `Message` /
  `Comment` / `Postback`. Both positional.

## 6. Models (`models.py`)

Typed, frozen dataclasses parsed from the Update JSON; each keeps `raw` (the original
dict) for forward-compat with new server fields.

```python
@dataclass(frozen=True)
class User:    id: str; username: Optional[str]
@dataclass(frozen=True)
class Channel: id: str; ig_user_id: str; username: Optional[str]
@dataclass(frozen=True)
class Message: id: str; text: str; from_user: User; channel: Channel; raw: dict
@dataclass(frozen=True)
class Comment: id: str; text: str; media_id: Optional[str]; from_user: User; channel: Channel; raw: dict
@dataclass(frozen=True)
class Postback: payload: str; from_user: User; channel: Channel; raw: dict
@dataclass(frozen=True)
class Update:  update_id: int; type: str; channel: Channel; from_user: User; \
               message: Optional[Message]; comment: Optional[Comment]; postback: Optional[Postback]; \
               timestamp: int; raw: dict
```
`Update.from_dict(d)` builds the right sub-object based on `type`. A malformed/unknown
`type` is logged and skipped (does not crash the loop), and the loop still advances the
offset past it so it isn't re-fetched forever.

## 7. Context (`context.py`)

Bound to a single update; knows its `channel.id` so the dev never threads it by hand.

```python
class Context:
    bot: "Bot"
    update: Update
    async def reply(self, text: str) -> None          # DM back to update.from_user.id
    async def reply_comment(self, text: str) -> None   # public reply; raises if update.comment is None
    async def send(self, to: str, text: str) -> None   # DM an arbitrary igsid on this channel
```
- `reply` → `client.send_message(channel_id=update.channel.id, to=update.from_user.id, text=...)`.
- `reply_comment` → `client.reply_comment(channel_id=update.channel.id, comment_id=update.comment.id, text=...)`; raises `RuntimeError` if called outside a comment handler.
- `send` → `client.send_message(channel_id=update.channel.id, to=to, text=...)`.

## 8. HTTP client (`client.py`)

Thin async wrapper over `httpx.AsyncClient`. One client instance per Bot, opened on
`run_polling` start, closed on shutdown.

```python
class ApiClient:
    def __init__(self, account_key: str, base_url: str, timeout: float = 30.0)
    async def get_updates(self, offset: int, limit: int, timeout: int, channel_id: Optional[str]) -> list[dict]
    async def send_message(self, channel_id: str, to: str, text: str) -> None
    async def reply_comment(self, channel_id: str, comment_id: str, text: str) -> None
    async def get_me(self, channel_id: str) -> dict
    async def aclose(self) -> None
```
- Sends `x-api-key: {account_key}`.
- `get_updates` uses an httpx read timeout > `poll_timeout` (so long-poll doesn't trip the client timeout).
- Non-2xx → raise: **401** → `AuthError`; anything else → `ApiError(status, body)`.

## 9. Polling loop (`bot.py`)

`run_polling()` is a thin **sync** entry point: `asyncio.run(self._run_polling())`.

`_run_polling()`:
1. Open the `ApiClient`.
2. `offset = 0`. Loop until stop:
   - `updates = await client.get_updates(offset, poll_limit, poll_timeout, channel_id)`
   - for each `u` (ascending): `update = Update.from_dict(u)`; `offset = update.update_id + 1`
     (advance offset **before** dispatch so a handler crash can't cause an infinite re-fetch);
     build `Context`; dispatch to the first matching handler; a handler exception is caught + logged.
   - empty list → loop again immediately (long-poll already waited server-side).
3. **Backoff:** on `httpx` transport errors or `ApiError` 5xx → sleep `min(2**n, 30)`s (reset on success), resume from the same `offset`. `AuthError` (401) → log a clear "invalid Account Key" message and stop.
4. **Shutdown:** install SIGINT/SIGTERM handlers (via the running loop) that flip the stop flag; finish the in-flight handler, `await client.aclose()`, return. Ctrl-C exits with no traceback.

**Dispatch (first-match):** iterate handlers in registration order; the first whose `kind`
matches the update's type **and** whose filter matches (text/regex for messages; always-true
for comment/postback) runs. No match → update is skipped (already acked via offset).

## 10. Errors (`errors.py`)

```python
class SdkError(Exception): ...
class ApiError(SdkError):   # non-2xx; carries .status and .body
class AuthError(ApiError):  # 401
```
Errors raised from `ctx.reply` / `ctx.send` / `ctx.reply_comment` propagate into the
handler (the dev can try/except). Errors during `get_updates` are handled by the loop's
backoff/stop logic (§9).

## 11. Testing strategy

pytest + **respx** (mocks httpx at the transport layer — no live network):

- **client.py:** each method hits the right URL/method, sends `x-api-key`, encodes the
  right query/body; 401 → `AuthError`, 500 → `ApiError`.
- **models.py:** `Update.from_dict` builds the correct sub-object for each `type`; unknown
  `type` is skipped, not raised; `raw` is preserved.
- **filters.py:** substring is case-insensitive; regex uses `re.search`; both-supplied raises.
- **dispatch:** first-match wins (registration order); no-match is a no-op.
- **loop:** offset advances to `last_id + 1` and acks; empty result re-polls; a handler
  exception is swallowed and the loop continues; 5xx triggers backoff then resumes; 401 stops.
- **context:** `reply` posts `{channel_id, to=from.id, text}`; `reply_comment` posts
  `{channel_id, comment_id, text}` and raises outside a comment; `send` targets the given igsid.
- **shutdown:** a stop signal ends the loop and closes the client.

Async tests via `pytest-asyncio`. The loop is structured so the stop flag + an injectable
`get_updates` make it testable without real time/network (tests feed canned update batches).

## 12. Packaging

- `pyproject.toml` (PEP 621), build backend **hatchling**, `src/` layout, package
  `social_media_automations`. Runtime dep: `httpx`. Dev deps: `pytest`, `pytest-asyncio`,
  `respx`. `pip install -e .` for local dev/examples.
- `README.md`: ~15-line quickstart + the handler/`ctx` reference.
- **No PyPI publish** this cycle (later, with a token). If pushed to GitHub later, use an
  owner/name distinct from the backend repo `book-up/social-media-automations`.

## 13. Scope

**In scope (this spec → first plan):** async `Bot` + decorators (`on_message` w/ text/regex,
`on_comment`, `on_postback`), first-match dispatch, typed models, `Context` (reply /
reply_comment / send), async `ApiClient` over the four `/bot/v1` endpoints, polling loop
with offset/ack + backoff + graceful shutdown, errors, pytest/respx suite, packaging,
README + quickstart example.

**Deferred (later specs):** webhook transport, `reply_dm` (comment→DM), `setDeliveryMode`
helper, rich messages (buttons/quick-replies), handler groups/middleware, retries config,
PyPI publish, a Node/TS SDK.
