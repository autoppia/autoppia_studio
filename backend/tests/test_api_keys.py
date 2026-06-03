import pytest
from fastapi import HTTPException

from app.routes.api_keys import _object_id, _verify_admin_key


def test_invalid_api_key_id_returns_bad_request():
    with pytest.raises(HTTPException) as exc:
        _object_id("not-an-object-id")

    assert exc.value.status_code == 400


def test_api_key_management_requires_admin_token_in_production(monkeypatch):
    monkeypatch.setenv("AUTOMATA_ENV", "production")
    monkeypatch.delenv("AUTOMATA_API_KEY_ADMIN_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        _verify_admin_key("")

    assert exc.value.status_code == 503
    assert exc.value.detail["error"]["code"] == "api_key_management_disabled"


def test_api_key_management_validates_admin_token(monkeypatch):
    monkeypatch.setenv("AUTOMATA_API_KEY_ADMIN_TOKEN", "secret-admin")

    with pytest.raises(HTTPException) as exc:
        _verify_admin_key("wrong")

    assert exc.value.status_code == 401
    assert exc.value.detail["error"]["code"] == "invalid_admin_key"
    _verify_admin_key("secret-admin")
