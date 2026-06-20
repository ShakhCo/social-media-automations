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
from .filters import make_payload_filter, make_text_filter
from .models import Update

logger = logging.getLogger("social_media_automations")

Handler = Tuple[str, Callable[[str], bool], Callable]


def _ensure_logging() -> None:
    """Give run_polling() readable console output by default, without clobbering a
    user's own logging config. If neither our logger nor the root has handlers, attach
    a simple stderr handler; otherwise just make sure our INFO records get through."""
    root = logging.getLogger()
    if logger.handlers or root.handlers:
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class Bot:
    def __init__(self, account_key: str, base_url: str = DEFAULT_BASE_URL, *,
                 poll_timeout: int = 25, poll_limit: int = 50,
                 channel_id: Optional[str] = None,
                 channel_ids: Optional[List[str]] = None) -> None:
        self.client = ApiClient(account_key, base_url)
        self._base_url = base_url
        self._poll_timeout = poll_timeout
        self._poll_limit = poll_limit
        ids = list(channel_ids or [])
        if channel_id:
            ids.append(channel_id)
        self._channel_ids: Optional[List[str]] = ids or None
        self._handlers: List[Handler] = []
        self._stop = False
        self._poll_task: Optional["asyncio.Task"] = None
        self._masked_key = (account_key[:12] + "…") if len(account_key) > 13 else account_key

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

    def on_postback(self, payload: Optional[str] = None, regex: Optional[str] = None) -> Callable:
        flt = make_payload_filter(payload, regex)
        def deco(fn: Callable) -> Callable:
            self._handlers.append(("postback", flt, fn))
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
        # If we're blocked in an in-flight long-poll (the common case when Ctrl+C is
        # pressed), cancel it so we exit immediately instead of waiting up to poll_timeout.
        # When stop() is called from inside a handler, it IS the poll task, so we skip the
        # cancel and let the _stop flag unwind the loop cleanly.
        task = self._poll_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    async def _poll_once(self, offset: int, timeout: Optional[int] = None) -> int:
        poll_timeout = self._poll_timeout if timeout is None else timeout
        rows = await self.client.get_updates(offset, self._poll_limit, poll_timeout, self._channel_ids)
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

    def _log_started(self) -> None:
        logger.info("● social-media-automations — polling started")
        logger.info(
            "  account: %s · channels: %s · press Ctrl+C to stop",
            self._masked_key, ", ".join(self._channel_ids) if self._channel_ids else "all bot-mode channels",
        )

    async def _run_polling(self) -> None:
        offset = 0
        backoff = 0
        started = False
        degraded = False  # True while we're riding out a backend outage / redeploy
        try:
            while not self._stop:
                try:
                    # The first poll uses timeout=0 so a bad key / connectivity problem
                    # surfaces IMMEDIATELY instead of after a full long-poll window.
                    self._poll_task = asyncio.ensure_future(
                        self._poll_once(offset, timeout=0 if not started else None)
                    )
                    offset = await self._poll_task
                    if not started:
                        started = True
                        self._log_started()
                    if degraded:
                        # We rode out an outage (e.g. a backend redeploy). The server
                        # keeps the update queue durably, so this poll returns anything
                        # that arrived while it was down — nothing was lost.
                        logger.info("● reconnected to backend")
                        degraded = False
                    backoff = 0
                except asyncio.CancelledError:
                    break  # stop() cancelled the in-flight poll (Ctrl+C)
                except AuthError:
                    logger.error("✗ invalid Account Key — check your key and try again")
                    break
                except (httpx.HTTPError, ApiError) as e:
                    status = getattr(e, "status", None)
                    # A genuine client error (bad request, blocked) is fatal — stop.
                    # But 408/429 are transient, and anything >= 500 means the backend
                    # is down or redeploying, so we ride it out and reconnect.
                    fatal = (
                        isinstance(e, ApiError)
                        and status is not None
                        and status < 500
                        and status not in (408, 429)
                    )
                    if fatal:
                        logger.error("✗ request rejected (%s) — stopping: %s", status, e)
                        break
                    # Reconnect quickly (cap at 5s) so a brief redeploy gap is barely felt,
                    # and stay quiet: one line when the outage starts, one when it clears.
                    delay = min(2 ** backoff, 5)
                    backoff += 1
                    reason = f"HTTP {status}" if status is not None else type(e).__name__
                    if not degraded:
                        logger.warning("● backend unavailable (%s) — reconnecting…", reason)
                        degraded = True
                    else:
                        logger.debug("still unavailable (%s); retrying in %ss", reason, delay)
                    await asyncio.sleep(delay)
        finally:
            self._poll_task = None
            await self.client.aclose()
            if started:
                logger.info("● stopped")

    def run_polling(self) -> None:
        _ensure_logging()

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
