import pytest
from fastapi import HTTPException

from app.routes import embed
from app.routes import companies
from app.request_scope import RequestScope


class _Companies:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                if key == "embedSettings.publicToken":
                    current = (doc.get("embedSettings") or {}).get("publicToken")
                else:
                    current = doc.get(key)
                if current != value:
                    matched = False
                    break
            if matched:
                return dict(doc)
        return None


class _CompanySettingsCollection:
    def __init__(self, doc):
        self.doc = dict(doc)

    async def find_one(self, query, projection=None):
        for key, value in query.items():
            if self.doc.get(key) != value:
                return None
        return dict(self.doc)

    async def update_one(self, query, update):
        for key, value in query.items():
            if self.doc.get(key) != value:
                return
        self.doc.update(update.get("$set", {}))


def _host_jwt(payload, secret="host-secret"):
    header = embed._b64(b'{"alg":"HS256","typ":"JWT"}')
    body = embed._b64(embed.json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = embed._b64(embed.hmac.new(secret.encode("utf-8"), f"{header}.{body}".encode("ascii"), embed.hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


@pytest.mark.asyncio
async def test_create_embed_session_validates_origin_and_signs_token(monkeypatch):
    monkeypatch.setattr(
        embed,
        "companies_collection",
        _Companies(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "embedSettings": {
                        "enabled": True,
                        "publicToken": "public-token",
                        "allowedOrigins": ["https://erp.example.com"],
                    },
                }
            ]
        ),
    )

    result = await embed.create_embed_session(
        embed.EmbedSessionRequest(token="public-token", userRef="employee-1"),
        origin="https://erp.example.com",
    )
    payload = embed._verify(result["sessionToken"], "public-token")

    assert result["companyId"] == "company-1"
    assert payload["companyId"] == "company-1"
    assert payload["email"] == "owner@example.com"
    assert payload["userRef"] == "employee-1"


@pytest.mark.asyncio
async def test_create_embed_session_rejects_unallowed_origin(monkeypatch):
    monkeypatch.setattr(
        embed,
        "companies_collection",
        _Companies(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "embedSettings": {
                        "enabled": True,
                        "publicToken": "public-token",
                        "allowedOrigins": ["https://erp.example.com"],
                    },
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await embed.create_embed_session(
            embed.EmbedSessionRequest(token="public-token", userRef="employee-1"),
            origin="https://evil.example.com",
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_embed_session_requires_and_uses_host_jwt(monkeypatch):
    monkeypatch.setattr(
        embed,
        "companies_collection",
        _Companies(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "embedSettings": {
                        "enabled": True,
                        "publicToken": "public-token",
                        "hostJwtSecret": "host-secret",
                    },
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await embed.create_embed_session(embed.EmbedSessionRequest(token="public-token", userRef="untrusted"))
    assert exc.value.status_code == 401

    result = await embed.create_embed_session(
        embed.EmbedSessionRequest(token="public-token", userRef="untrusted", hostJwt=_host_jwt({"sub": "employee-42", "role": "broker"}))
    )
    payload = embed._verify(result["sessionToken"], "public-token")

    assert payload["userRef"] == "employee-42"
    assert payload["hostClaims"] == {"sub": "employee-42", "role": "broker"}


def test_company_serializer_redacts_embed_host_jwt_secret():
    serialized = companies._serialize(
        {
            "companyId": "company-1",
            "email": "owner@example.com",
            "name": "Company",
            "embedSettings": {
                "enabled": True,
                "publicToken": "public-token",
                "hostJwtSecret": "host-secret",
                "allowedOrigins": ["https://erp.example.com"],
            },
        }
    )

    assert serialized["embedSettings"]["hostJwtConfigured"] is True
    assert "hostJwtSecret" not in serialized["embedSettings"]


@pytest.mark.asyncio
async def test_widget_js_uses_script_origin_for_frame():
    response = await embed.embed_widget_js()
    body = response.body.decode("utf-8")

    assert "scriptUrl.origin" in body
    assert "new URL('/embed/v1/frame',scriptUrl.origin)" in body
    assert "data-user-ref" in body
    assert "data-host-jwt" in body


@pytest.mark.asyncio
async def test_embed_frame_posts_user_ref_and_host_jwt():
    response = await embed.embed_frame("public-token", userRef="employee-1", hostJwt="jwt-1")
    body = response.body.decode("utf-8")

    assert 'var embedUserRef="employee-1";' in body
    assert 'var embedHostJwt="jwt-1";' in body
    assert "hostJwt:embedHostJwt" in body


def test_company_serializer_reports_cleared_embed_host_jwt_secret():
    serialized = companies._serialize(
        {
            "companyId": "company-1",
            "email": "owner@example.com",
            "name": "Company",
            "embedSettings": {
                "enabled": True,
                "publicToken": "public-token",
                "hostJwtSecret": "",
            },
        }
    )

    assert serialized["embedSettings"]["hostJwtConfigured"] is False


@pytest.mark.asyncio
async def test_update_company_embed_settings_preserves_and_clears_secret(monkeypatch):
    collection = _CompanySettingsCollection(
        {
            "companyId": "company-1",
            "email": "owner@example.com",
            "name": "Company",
            "embedSettings": {"hostJwtSecret": "old-secret"},
        }
    )
    monkeypatch.setattr(companies, "companies_collection", collection)
    scope = RequestScope(email="owner@example.com", token_email="owner@example.com")

    preserved = await companies.update_company_embed_settings(
        "company-1",
        companies.CompanyEmbedSettingsRequest(enabled=True, publicToken="public-token", allowedOrigins=[]),
        scope,
    )
    assert collection.doc["embedSettings"]["hostJwtSecret"] == "old-secret"
    assert preserved["embedSettings"]["hostJwtConfigured"] is True
    assert "hostJwtSecret" not in preserved["embedSettings"]

    cleared = await companies.update_company_embed_settings(
        "company-1",
        companies.CompanyEmbedSettingsRequest(enabled=True, publicToken="public-token", clearHostJwtSecret=True),
        scope,
    )
    assert collection.doc["embedSettings"]["hostJwtSecret"] == ""
    assert cleared["embedSettings"]["hostJwtConfigured"] is False
