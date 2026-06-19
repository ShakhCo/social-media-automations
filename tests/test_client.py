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
