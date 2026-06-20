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

    async def get_updates(self, offset: int, limit: int, timeout: int, channel_ids: Optional[list] = None) -> list:
        params = {"offset": offset, "limit": limit, "timeout": timeout}
        if channel_ids:
            params["channel_ids"] = ",".join(channel_ids)
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

    async def send_action(self, channel_id: str, to: str, action: str) -> None:
        resp = await self._http.post(
            "/bot/v1/sendAction", json={"channel_id": channel_id, "to": to, "action": action}
        )
        self._check(resp)

    async def get_me(self, channel_id: str) -> dict:
        resp = await self._http.get("/bot/v1/getMe", params={"channel_id": channel_id})
        self._check(resp)
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
