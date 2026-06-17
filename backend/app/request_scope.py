from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class RequestScope:
    email: str = ""
    token_email: str = ""

    def require_email(self, fallback: str = "") -> str:
        if fallback:
            self.assert_email(fallback)
        email = self.email or fallback
        if not email:
            raise HTTPException(status_code=401, detail="Authentication scope is required")
        return email

    def assert_email(self, email: str) -> None:
        if self.token_email and email and self.token_email != email:
            raise HTTPException(status_code=403, detail="Request email does not match authenticated user")

    def owns(self, doc: dict[str, Any] | None) -> bool:
        if not doc:
            return False
        if not self.email:
            return False
        return str(doc.get("email") or "") == self.email

    def assert_owns(self, doc: dict[str, Any] | None, *, not_found: str = "Not found") -> dict[str, Any]:
        if not doc or not self.owns(doc):
            raise HTTPException(status_code=404, detail=not_found)
        return doc


def _decode_token_email(token: str) -> str:
    if not token:
        return ""
    secret = os.getenv("JWT_SECRET", "autoppia-automata-secret-key")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not payload.get("email"):
        raise HTTPException(status_code=401, detail="Token missing email")
    return str(payload.get("email") or "")


async def _request_email(request: Request) -> str:
    email = str(request.query_params.get("email") or "").strip()
    if email:
        return email
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            return str(body.get("email") or "").strip()
    return ""


async def get_request_scope(request: Request) -> RequestScope:
    credentials: HTTPAuthorizationCredentials | None = await bearer(request)
    raw_token = credentials.credentials if credentials else str(request.cookies.get("access_token") or "")
    token_email = _decode_token_email(raw_token)
    request_email = await _request_email(request)
    if token_email and request_email and token_email != request_email:
        raise HTTPException(status_code=403, detail="Request email does not match authenticated user")
    return RequestScope(email=token_email or request_email, token_email=token_email)


def coerce_request_scope(scope: Any) -> RequestScope:
    return scope if isinstance(scope, RequestScope) else RequestScope()
