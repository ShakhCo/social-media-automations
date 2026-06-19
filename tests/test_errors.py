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
