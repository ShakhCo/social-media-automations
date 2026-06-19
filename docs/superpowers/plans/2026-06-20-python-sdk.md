# Python SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `social-media-automations` async Python SDK — a `python-telegram-bot`–style client over the deployed `/bot/v1` Bot API (register handlers, `run_polling()`).

**Architecture:** A `src/`-layout package with single-responsibility modules: `errors` → `models` → `filters` → `client` (async httpx) → `context` → `bot` (registry + polling loop). Built bottom-up so each task tests on a green foundation. Async throughout (asyncio + httpx); polling with offset/ack, backoff, and graceful shutdown.

**Tech Stack:** Python 3.9+, httpx (async), dataclasses, pytest + pytest-asyncio + respx (mocked transport, no network), hatchling build backend.

**Reference design:** `docs/superpowers/specs/2026-06-20-python-sdk-design.md`.

## Global Constraints

- **Package (pip) name:** `social-media-automations`; **import name:** `social_media_automations`; `src/` layout.
- **Python floor 3.9.** Every module starts with `from __future__ import annotations` so `X | None` / `list[dict]` hints are legal on 3.9. Do NOT use `match` statements or other 3.10+ syntax.
- **Async only.** Handlers are `async def handler(obj, ctx)`. Public sync entry point is `Bot.run_polling()` (wraps `asyncio.run`).
- **Auth:** single Account Key sent as header `x-api-key: <key>`. No other credential.
- **API base URL default:** `https://social-media-api.automations.uz`. All endpoints under `/bot/v1`.
- **Endpoints:** `GET /bot/v1/getUpdates` (query `offset,limit,timeout,channel_id?`) → `{"result": [...]}`; `POST /bot/v1/sendMessage` `{channel_id,to,text}`; `POST /bot/v1/replyComment` `{channel_id,comment_id,text}`; `GET /bot/v1/getMe` (query `channel_id`).
- **Update contract:** `{update_id:int, type:"message"|"comment"|"postback", channel:{id,ig_user_id,username}, from:{id,username}, message?:{id,text}, comment?:{id,text,media_id}, postback?:{payload}, timestamp:int}`. Only the sub-object matching `type` is present.
- **Dispatch:** flat registry, **first-match wins** (registration order); one update → at most one handler.
- **Offset/ack:** `offset` starts at 0; after building each update, set `offset = update_id + 1` BEFORE dispatch (so a handler crash never causes infinite re-fetch). Passing the next `offset` acks server-side.
- **Errors:** non-2xx → raise; 401 → `AuthError`, else `ApiError(status, body)`. Loop: 401 fatal (stop), 5xx/network → exponential backoff `min(2**n, 30)`s.
- **YAGNI / deferred (do NOT build):** webhooks, `reply_dm` (comment→DM), `setDeliveryMode`, rich messages/buttons, handler groups, PyPI publish.

---

### Task 1: Project scaffold + packaging + errors

**Files:**
- Create: `pyproject.toml`
- Create: `src/social_media_automations/__init__.py`
- Create: `src/social_media_automations/errors.py`
- Create: `tests/__init__.py`
- Create: `tests/test_errors.py`
- Create: `README.md` (stub; filled in Task 8)

**Interfaces:**
- Produces: `SdkError(Exception)`, `ApiError(SdkError)` with `.status: int` and `.body: str`, `AuthError(ApiError)`. Package import name `social_media_automations`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "social-media-automations"
version = "0.1.0"
description = "Async Python SDK for the social-media-automations Instagram Bot API"
requires-python = ">=3.9"
dependencies = ["httpx>=0.24"]

[project.optional-dependencies]
dev = ["pytest>=7", "pytest-asyncio>=0.21", "respx>=0.20"]

[tool.hatch.build.targets.wheel]
packages = ["src/social_media_automations"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty test package + README stub**

`tests/__init__.py`: empty file.
`README.md`:
```markdown
# social-media-automations (Python SDK)

Async Python client for the Instagram Bot API. See `docs/` for the design.
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_errors.py
from social_media_automations.errors import SdkError, ApiError, AuthError


def test_api_error_carries_status_and_body():
    e = ApiError(500, "boom")
    assert e.status == 500
    assert e.body == "boom"
    assert isinstance(e, SdkError)


def test_auth_error_is_an_api_error_with_401():
    e = AuthError(401, "bad key")
    assert isinstance(e, ApiError)
    assert e.status == 401
```

- [ ] **Step 4: Run it to verify it fails**

Run: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && python -m pytest tests/test_errors.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'social_media_automations.errors'`.
(After this task the venv exists; later tasks reuse `. .venv/bin/activate`.)

- [ ] **Step 5: Implement `errors.py` + `__init__.py`**

```python
# src/social_media_automations/errors.py
from __future__ import annotations


class SdkError(Exception):
    """Base class for all SDK errors."""


class ApiError(SdkError):
    """A non-2xx response from the Bot API."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"API error {status}: {body}")
        self.status = status
        self.body = body


class AuthError(ApiError):
    """A 401 from the Bot API (bad/blocked Account Key)."""
```

```python
# src/social_media_automations/__init__.py
from __future__ import annotations

from .errors import SdkError, ApiError, AuthError

__all__ = ["SdkError", "ApiError", "AuthError"]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/test_errors.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/social_media_automations/__init__.py src/social_media_automations/errors.py tests/__init__.py tests/test_errors.py README.md
git commit -m "feat: project scaffold, packaging, error types"
```

---

### Task 2: Models (`Update.from_dict` + sub-objects)

**Files:**
- Create: `src/social_media_automations/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces (frozen dataclasses):
  - `User(id: str, username: Optional[str])`
  - `Channel(id: str, ig_user_id: str, username: Optional[str])`
  - `Message(id: str, text: str, from_user: User, channel: Channel, raw: dict)`
  - `Comment(id: str, text: str, media_id: Optional[str], from_user: User, channel: Channel, raw: dict)`
  - `Postback(payload: str, from_user: User, channel: Channel, raw: dict)`
  - `Update(update_id: int, type: str, channel: Channel, from_user: User, message: Optional[Message], comment: Optional[Comment], postback: Optional[Postback], timestamp: int, raw: dict)`
  - `Update.from_dict(d: dict) -> Optional["Update"]` — returns `None` for an unknown/malformed `type` (caller skips it).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from social_media_automations.models import Update, Message, Comment, Postback

MSG = {
    "update_id": 7, "type": "message",
    "channel": {"id": "ch-1", "ig_user_id": "178", "username": "salon"},
    "from": {"id": "igsid-9", "username": "shopper"},
    "message": {"id": "mid-7", "text": "can I book?"},
    "timestamp": 1718800000000,
}
CMT = {
    "update_id": 8, "type": "comment",
    "channel": {"id": "ch-1", "ig_user_id": "178", "username": "salon"},
    "from": {"id": "u1", "username": None},
    "comment": {"id": "c-77", "text": "price?", "media_id": "m-5"},
    "timestamp": 1718800001000,
}
PB = {
    "update_id": 9, "type": "postback",
    "channel": {"id": "ch-1", "ig_user_id": "178", "username": "salon"},
    "from": {"id": "u1", "username": "x"},
    "postback": {"payload": "book"},
    "timestamp": 1718800002000,
}


def test_parses_message_update():
    u = Update.from_dict(MSG)
    assert u.update_id == 7 and u.type == "message"
    assert isinstance(u.message, Message)
    assert u.message.id == "mid-7" and u.message.text == "can I book?"
    assert u.from_user.username == "shopper"
    assert u.channel.id == "ch-1"
    assert u.comment is None and u.postback is None
    assert u.raw is MSG


def test_parses_comment_update():
    u = Update.from_dict(CMT)
    assert isinstance(u.comment, Comment)
    assert u.comment.id == "c-77" and u.comment.media_id == "m-5"
    assert u.message is None


def test_parses_postback_update():
    u = Update.from_dict(PB)
    assert isinstance(u.postback, Postback)
    assert u.postback.payload == "book"


def test_unknown_type_returns_none():
    assert Update.from_dict({"update_id": 1, "type": "reaction"}) is None


def test_malformed_returns_none():
    assert Update.from_dict({"nope": True}) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'social_media_automations.models'`.

- [ ] **Step 3: Implement `models.py`**

```python
# src/social_media_automations/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class User:
    id: str
    username: Optional[str]


@dataclass(frozen=True)
class Channel:
    id: str
    ig_user_id: str
    username: Optional[str]


@dataclass(frozen=True)
class Message:
    id: str
    text: str
    from_user: User
    channel: Channel
    raw: dict


@dataclass(frozen=True)
class Comment:
    id: str
    text: str
    media_id: Optional[str]
    from_user: User
    channel: Channel
    raw: dict


@dataclass(frozen=True)
class Postback:
    payload: str
    from_user: User
    channel: Channel
    raw: dict


@dataclass(frozen=True)
class Update:
    update_id: int
    type: str
    channel: Channel
    from_user: User
    message: Optional[Message]
    comment: Optional[Comment]
    postback: Optional[Postback]
    timestamp: int
    raw: dict

    @classmethod
    def from_dict(cls, d: dict) -> Optional["Update"]:
        try:
            kind = d["type"]
            ch = d["channel"]
            channel = Channel(id=ch["id"], ig_user_id=ch["ig_user_id"], username=ch.get("username"))
            f = d.get("from") or {}
            user = User(id=f.get("id", ""), username=f.get("username"))
            message = comment = postback = None
            if kind == "message":
                m = d["message"]
                message = Message(id=m["id"], text=m.get("text", ""), from_user=user, channel=channel, raw=d)
            elif kind == "comment":
                c = d["comment"]
                comment = Comment(id=c["id"], text=c.get("text", ""), media_id=c.get("media_id"),
                                  from_user=user, channel=channel, raw=d)
            elif kind == "postback":
                p = d["postback"]
                postback = Postback(payload=p.get("payload", ""), from_user=user, channel=channel, raw=d)
            else:
                return None
            return cls(update_id=d["update_id"], type=kind, channel=channel, from_user=user,
                       message=message, comment=comment, postback=postback,
                       timestamp=d.get("timestamp", 0), raw=d)
        except (KeyError, TypeError):
            return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_models.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/social_media_automations/models.py tests/test_models.py
git commit -m "feat: typed Update models + from_dict parsing"
```

---

### Task 3: Filters (text / regex matching)

**Files:**
- Create: `src/social_media_automations/filters.py`
- Create: `tests/test_filters.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `make_text_filter(text: Optional[str], regex: Optional[str]) -> Callable[[str], bool]`. Both `None` → always-true. `text` → case-insensitive substring. `regex` → `re.search`. Both set → raise `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filters.py
import pytest
from social_media_automations.filters import make_text_filter


def test_no_args_matches_everything():
    f = make_text_filter(None, None)
    assert f("anything") is True
    assert f("") is True


def test_text_is_case_insensitive_substring():
    f = make_text_filter("price", None)
    assert f("what is the PRICE?") is True
    assert f("cost") is False


def test_regex_uses_search():
    f = make_text_filter(None, r"\bbook\b")
    assert f("i want to book now") is True
    assert f("textbook") is False


def test_both_args_raises():
    with pytest.raises(ValueError):
        make_text_filter("a", "b")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_filters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'social_media_automations.filters'`.

- [ ] **Step 3: Implement `filters.py`**

```python
# src/social_media_automations/filters.py
from __future__ import annotations

import re
from typing import Callable, Optional


def make_text_filter(text: Optional[str], regex: Optional[str]) -> Callable[[str], bool]:
    if text is not None and regex is not None:
        raise ValueError("pass either text= or regex=, not both")
    if text is not None:
        needle = text.lower()
        return lambda s: needle in (s or "").lower()
    if regex is not None:
        pattern = re.compile(regex)
        return lambda s: pattern.search(s or "") is not None
    return lambda s: True
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_filters.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/social_media_automations/filters.py tests/test_filters.py
git commit -m "feat: text/regex message filters"
```

---

### Task 4: Async HTTP client (`ApiClient`)

**Files:**
- Create: `src/social_media_automations/client.py`
- Create: `tests/test_client.py`

**Interfaces:**
- Consumes: `ApiError`, `AuthError` from `errors`.
- Produces:
  - `DEFAULT_BASE_URL = "https://social-media-api.automations.uz"`
  - `ApiClient(account_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0)`
  - `async get_updates(offset: int, limit: int, timeout: int, channel_id: Optional[str]) -> list[dict]` → returns the `result` array. The httpx read timeout is `self._timeout + timeout` so long-poll doesn't trip it.
  - `async send_message(channel_id: str, to: str, text: str) -> None`
  - `async reply_comment(channel_id: str, comment_id: str, text: str) -> None`
  - `async get_me(channel_id: str) -> dict`
  - `async aclose() -> None`
  - All requests send header `x-api-key`. Non-2xx: 401 → `AuthError(401, body)`, else `ApiError(status, body)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
import httpx
import pytest
import respx
from social_media_automations.client import ApiClient, DEFAULT_BASE_URL
from social_media_automations.errors import ApiError, AuthError

BASE = DEFAULT_BASE_URL


@respx.mock
async def test_get_updates_sends_key_and_params_returns_result():
    route = respx.get(f"{BASE}/bot/v1/getUpdates").mock(
        return_value=httpx.Response(200, json={"result": [{"update_id": 1}]})
    )
    c = ApiClient("ak_x")
    out = await c.get_updates(offset=5, limit=50, timeout=25, channel_id="ch-1")
    await c.aclose()
    assert out == [{"update_id": 1}]
    req = route.calls.last.request
    assert req.headers["x-api-key"] == "ak_x"
    assert req.url.params["offset"] == "5"
    assert req.url.params["channel_id"] == "ch-1"


@respx.mock
async def test_get_updates_omits_channel_id_when_none():
    route = respx.get(f"{BASE}/bot/v1/getUpdates").mock(
        return_value=httpx.Response(200, json={"result": []})
    )
    c = ApiClient("ak_x")
    await c.get_updates(offset=0, limit=50, timeout=0, channel_id=None)
    await c.aclose()
    assert "channel_id" not in route.calls.last.request.url.params


@respx.mock
async def test_send_message_posts_body():
    route = respx.post(f"{BASE}/bot/v1/sendMessage").mock(return_value=httpx.Response(201, json={"ok": True}))
    c = ApiClient("ak_x")
    await c.send_message(channel_id="ch-1", to="igsid-9", text="hi")
    await c.aclose()
    import json
    body = json.loads(route.calls.last.request.content)
    assert body == {"channel_id": "ch-1", "to": "igsid-9", "text": "hi"}


@respx.mock
async def test_reply_comment_posts_body():
    route = respx.post(f"{BASE}/bot/v1/replyComment").mock(return_value=httpx.Response(201, json={"ok": True}))
    c = ApiClient("ak_x")
    await c.reply_comment(channel_id="ch-1", comment_id="c-77", text="thanks")
    await c.aclose()
    import json
    body = json.loads(route.calls.last.request.content)
    assert body == {"channel_id": "ch-1", "comment_id": "c-77", "text": "thanks"}


@respx.mock
async def test_401_raises_auth_error():
    respx.get(f"{BASE}/bot/v1/getUpdates").mock(return_value=httpx.Response(401, text="bad key"))
    c = ApiClient("ak_x")
    with pytest.raises(AuthError):
        await c.get_updates(0, 50, 0, None)
    await c.aclose()


@respx.mock
async def test_500_raises_api_error():
    respx.post(f"{BASE}/bot/v1/sendMessage").mock(return_value=httpx.Response(500, text="boom"))
    c = ApiClient("ak_x")
    with pytest.raises(ApiError) as ei:
        await c.send_message("ch-1", "to", "t")
    await c.aclose()
    assert ei.value.status == 500
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'social_media_automations.client'`.

- [ ] **Step 3: Implement `client.py`**

```python
# src/social_media_automations/client.py
from __future__ import annotations

from typing import Optional

import httpx

from .errors import ApiError, AuthError

DEFAULT_BASE_URL = "https://social-media-api.automations.uz"


class ApiClient:
    def __init__(self, account_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"x-api-key": account_key},
            timeout=timeout,
        )

    def _check(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        if resp.status_code == 401:
            raise AuthError(401, resp.text)
        raise ApiError(resp.status_code, resp.text)

    async def get_updates(self, offset: int, limit: int, timeout: int, channel_id: Optional[str]) -> list:
        params = {"offset": offset, "limit": limit, "timeout": timeout}
        if channel_id is not None:
            params["channel_id"] = channel_id
        # Read timeout must outlast the server long-poll window.
        resp = await self._http.get("/bot/v1/getUpdates", params=params, timeout=self._timeout + timeout)
        self._check(resp)
        return resp.json().get("result", [])

    async def send_message(self, channel_id: str, to: str, text: str) -> None:
        resp = await self._http.post("/bot/v1/sendMessage", json={"channel_id": channel_id, "to": to, "text": text})
        self._check(resp)

    async def reply_comment(self, channel_id: str, comment_id: str, text: str) -> None:
        resp = await self._http.post(
            "/bot/v1/replyComment", json={"channel_id": channel_id, "comment_id": comment_id, "text": text}
        )
        self._check(resp)

    async def get_me(self, channel_id: str) -> dict:
        resp = await self._http.get("/bot/v1/getMe", params={"channel_id": channel_id})
        self._check(resp)
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_client.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/social_media_automations/client.py tests/test_client.py
git commit -m "feat: async ApiClient over /bot/v1 (httpx)"
```

---

### Task 5: Context (`ctx.reply` / `reply_comment` / `send`)

**Files:**
- Create: `src/social_media_automations/context.py`
- Create: `tests/test_context.py`

**Interfaces:**
- Consumes: `Update` (models), an object exposing `client: ApiClient` (the Bot — duck-typed in tests).
- Produces: `Context(bot, update: Update)` with:
  - `async reply(text: str)` → `client.send_message(channel_id=update.channel.id, to=update.from_user.id, text=text)`
  - `async reply_comment(text: str)` → raises `RuntimeError` if `update.comment is None`, else `client.reply_comment(channel_id=update.channel.id, comment_id=update.comment.id, text=text)`
  - `async send(to: str, text: str)` → `client.send_message(channel_id=update.channel.id, to=to, text=text)`
  - exposes `.bot` and `.update`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_context.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_context.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'social_media_automations.context'`.

- [ ] **Step 3: Implement `context.py`**

```python
# src/social_media_automations/context.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_context.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/social_media_automations/context.py tests/test_context.py
git commit -m "feat: Context reply/reply_comment/send"
```

---

### Task 6: Bot — registry + decorators + dispatch

**Files:**
- Create: `src/social_media_automations/bot.py`
- Modify: `src/social_media_automations/__init__.py` (export `Bot` + models)
- Create: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `ApiClient`, `DEFAULT_BASE_URL`, `Context`, `Update`, `make_text_filter`, models.
- Produces:
  - `Bot(account_key, base_url=DEFAULT_BASE_URL, *, poll_timeout=25, poll_limit=50, channel_id=None)`. Lazily creates `self.client` (an `ApiClient`) — created in the constructor.
  - Decorators (each returns the undecorated fn so stacking works):
    - `on_message(text: Optional[str] = None, regex: Optional[str] = None)`
    - `on_comment()`
    - `on_postback()`
  - `async dispatch(update: Update) -> bool` — runs the first matching handler with a fresh `Context`, returns `True` if one ran, `False` if none matched. A handler exception is caught + logged (returns `True` — it matched).
  - Internal registry: list of `(kind, filter_fn, handler)` in registration order.

> The polling loop is added in Task 7. This task only covers registration + dispatch, which is unit-testable without network.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py
from social_media_automations import Bot
from social_media_automations.models import Update

MSG = {"update_id": 1, "type": "message", "channel": {"id": "ch", "ig_user_id": "178", "username": "s"},
       "from": {"id": "u", "username": "x"}, "message": {"id": "m", "text": "what PRICE?"}, "timestamp": 1}
CMT = {"update_id": 2, "type": "comment", "channel": {"id": "ch", "ig_user_id": "178", "username": "s"},
       "from": {"id": "u", "username": "x"}, "comment": {"id": "c", "text": "hi", "media_id": None}, "timestamp": 1}


def make_bot(monkeypatch=None):
    return Bot(account_key="ak_x")


async def test_first_match_wins():
    bot = make_bot()
    hits = []

    @bot.on_message(text="price")
    async def a(msg, ctx): hits.append("a")

    @bot.on_message()
    async def b(msg, ctx): hits.append("b")

    ran = await bot.dispatch(Update.from_dict(MSG))
    assert ran is True
    assert hits == ["a"]  # only the first matching handler


async def test_comment_handler_only_gets_comments():
    bot = make_bot()
    seen = []

    @bot.on_comment()
    async def c(cm, ctx): seen.append("c")

    @bot.on_message()
    async def m(msg, ctx): seen.append("m")

    await bot.dispatch(Update.from_dict(CMT))
    assert seen == ["c"]


async def test_no_match_returns_false():
    bot = make_bot()

    @bot.on_message(text="zzz")
    async def a(msg, ctx): ...

    assert await bot.dispatch(Update.from_dict(MSG)) is False


async def test_handler_exception_is_swallowed():
    bot = make_bot()

    @bot.on_message()
    async def boom(msg, ctx): raise ValueError("kaboom")

    # does not raise; counts as matched
    assert await bot.dispatch(Update.from_dict(MSG)) is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_dispatch.py -q`
Expected: FAIL — `ImportError: cannot import name 'Bot'`.

- [ ] **Step 3: Implement `bot.py` (registry + dispatch only)**

```python
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
```

- [ ] **Step 4: Update `__init__.py` exports**

```python
# src/social_media_automations/__init__.py
from __future__ import annotations

from .bot import Bot
from .context import Context
from .models import Update, Message, Comment, Postback, User, Channel
from .errors import SdkError, ApiError, AuthError

__all__ = [
    "Bot", "Context",
    "Update", "Message", "Comment", "Postback", "User", "Channel",
    "SdkError", "ApiError", "AuthError",
]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_dispatch.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/social_media_automations/bot.py src/social_media_automations/__init__.py tests/test_dispatch.py
git commit -m "feat: Bot registry, decorators, first-match dispatch"
```

---

### Task 7: Polling loop — offset/ack, backoff, graceful shutdown

**Files:**
- Modify: `src/social_media_automations/bot.py` (add `_poll_once`, `_run_polling`, `run_polling`, `stop`)
- Create: `tests/test_polling.py`

**Interfaces:**
- Consumes: own `dispatch`, `self.client.get_updates`, `AuthError`, `ApiError`.
- Produces:
  - `async _poll_once(offset: int) -> int` — fetches one batch from `offset`, parses each row, sets `offset = update_id + 1` BEFORE dispatch, skips rows that parse to `None` (still advancing offset past them using the row's `update_id` when present), returns the new `offset`.
  - `async _run_polling() -> None` — the async loop: repeatedly `_poll_once`; backoff `min(2**n, 30)`s on `httpx.HTTPError`/`ApiError` 5xx; stop on `AuthError`; honor `self._stop`; `await self.client.aclose()` on exit.
  - `run_polling() -> None` — sync entry: installs SIGINT/SIGTERM → `self.stop()`, then `asyncio.run(self._run_polling())`. Catches `KeyboardInterrupt` so Ctrl-C exits cleanly.
  - `stop() -> None` — sets the stop flag.

> Tests drive `_poll_once` / `_run_polling` directly with a fake client (no real network, no real sleeping — patch `asyncio.sleep`). `run_polling()` itself (signal wiring) is exercised lightly via a fake `_run_polling`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_polling.py -q`
Expected: FAIL — `AttributeError: 'Bot' object has no attribute '_poll_once'`.

- [ ] **Step 3: Implement the loop in `bot.py`**

Add imports at the top of `bot.py`:
```python
import asyncio
import signal
import httpx
from .errors import ApiError, AuthError
```
Add to `__init__`: `self._stop = False`.
Add these methods to `Bot`:
```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_polling.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: all tests pass (Tasks 1–7).

- [ ] **Step 6: Commit**

```bash
git add src/social_media_automations/bot.py tests/test_polling.py
git commit -m "feat: polling loop with offset/ack, backoff, graceful shutdown"
```

---

### Task 8: Quickstart example + README

**Files:**
- Create: `examples/quickstart.py`
- Modify: `README.md`
- Create: `tests/test_example_imports.py`

**Interfaces:**
- Consumes: the public API (`Bot`, decorators, `ctx`).
- Produces: a runnable example + docs. No new library code.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_example_imports.py
import ast
import pathlib


def test_quickstart_is_valid_python_and_uses_public_api():
    src = pathlib.Path("examples/quickstart.py").read_text()
    ast.parse(src)  # raises SyntaxError if malformed
    assert "from social_media_automations import Bot" in src
    assert "run_polling()" in src
    assert "@app.on_message" in src
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_example_imports.py -q`
Expected: FAIL — `FileNotFoundError: examples/quickstart.py`.

- [ ] **Step 3: Write the example**

```python
# examples/quickstart.py
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
    await ctx.reply(f"Salom, {msg.from_user.username or 'do\\'st'}! Nima bilan yordam beray?")


@app.on_comment()
async def thank(comment, ctx):
    await ctx.reply_comment("Rahmat! 🙌")


@app.on_postback()
async def button(pb, ctx):
    if pb.payload == "book":
        await ctx.reply("Keling, band qilamiz!")


if __name__ == "__main__":
    app.run_polling()
```

- [ ] **Step 4: Write the README**

```markdown
# social-media-automations (Python SDK)

Async Python client for the Instagram Bot API — register handlers, call `run_polling()`.

## Install
```bash
pip install -e .
```

## Quickstart
```python
from social_media_automations import Bot

app = Bot(account_key="ak_...")   # your Account Key

@app.on_message()
async def on_dm(msg, ctx):
    await ctx.reply(f"Salom {msg.from_user.username}!")

@app.on_message(text="price")     # case-insensitive substring; or regex="..."
async def price(msg, ctx):
    await ctx.reply("72 000 so'm/oy")

@app.on_comment()
async def on_comment(c, ctx):
    await ctx.reply_comment("Rahmat!")

@app.on_postback()
async def on_btn(pb, ctx):
    if pb.payload == "book":
        await ctx.reply("Keling, band qilamiz!")

app.run_polling()
```

## Handler reference
- `@app.on_message(text=None, regex=None)` — DMs. `text` = case-insensitive substring; `regex` = `re.search`; pass at most one.
- `@app.on_comment()` — public comments.
- `@app.on_postback()` — button/ice-breaker taps (`pb.payload`).

Handlers are `async def handler(obj, ctx)`. First matching handler wins.

## Context (`ctx`)
- `await ctx.reply(text)` — DM the sender.
- `await ctx.reply_comment(text)` — public reply (comment handlers only).
- `await ctx.send(to, text)` — DM an arbitrary IG-scoped id on this channel.

## Notes
- One channel must be in **bot mode** first (`POST /bot/v1/setDeliveryMode`).
- Polling is at-least-once; `msg.id` / `comment.id` are stable for dedup.
- `Ctrl-C` stops the bot cleanly.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_example_imports.py -q`
Expected: PASS (1 passed).

- [ ] **Step 6: Run the whole suite + a smoke import**

Run: `python -m pytest -q && python -c "import social_media_automations as s; print(sorted(s.__all__))"`
Expected: all tests pass; the import prints the export list with no error.

- [ ] **Step 7: Commit**

```bash
git add examples/quickstart.py README.md tests/test_example_imports.py
git commit -m "docs: quickstart example + README"
```

---

## Self-Review

**1. Spec coverage:**
- Async `Bot` + decorators (text/regex, comment, postback) → Tasks 6. ✅
- First-match dispatch → Task 6. ✅
- Typed models + `from_dict` (unknown type skipped) → Task 2. ✅
- `Context` reply/reply_comment/send → Task 5. ✅
- Async `ApiClient` over the 4 endpoints, `x-api-key`, 401/5xx handling, long-poll read timeout → Task 4. ✅
- Polling loop: offset/ack, backoff, graceful shutdown → Task 7. ✅
- Errors (`SdkError`/`ApiError`/`AuthError`) → Task 1. ✅
- Filters (substring/regex, both-raises) → Task 3. ✅
- Packaging (pyproject, src-layout, hatchling, deps) → Task 1. ✅
- README + quickstart → Task 8. ✅
- pytest + pytest-asyncio + respx → Tasks 1 (config), 4 (respx), all (asyncio_mode=auto). ✅
- Deferred items (webhook, reply_dm, setDeliveryMode, rich, groups, PyPI) → not built. ✅

**2. Placeholder scan:** No TBD/"handle errors"/"similar to Task N". One inline note in Task 7 corrects the first test to call the real `_poll_once` (and explicitly drops the throwaway helper) — the implementer must use that version. Complete code in every step.

**3. Type consistency:**
- `ApiClient.get_updates(offset, limit, timeout, channel_id)` — Tasks 4, 7 agree.
- `client.send_message(channel_id, to, text)` / `reply_comment(channel_id, comment_id, text)` — Tasks 4, 5 agree.
- `Update.from_dict` returns `Optional[Update]`; `dispatch` + `_poll_once` handle `None` — Tasks 2, 6, 7 agree.
- `make_text_filter(text, regex)` — Tasks 3, 6 agree.
- `Context(bot, update)` and `bot.client` attribute — Tasks 5, 6, 7 agree (tests swap `bot.client` with a fake).
- `Bot(account_key, base_url=DEFAULT_BASE_URL, *, poll_timeout, poll_limit, channel_id)` — Tasks 6, 7 agree.

**Known follow-ups (non-blocking, for final review):**
- `_poll_once` advances offset by the row's `update_id` even for skipped (unknown-type) rows, so a future event type can't wedge the loop — matches the spec's "advance past it" intent.
- The first Task-7 test is given in two forms; the implementer uses the corrected `_poll_once` version per the inline note.
