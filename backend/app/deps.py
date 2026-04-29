import os
import logging

import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "autoppia-automata-secret-key")
JWT_ALGORITHM = "HS256"


async def get_current_email(request: Request) -> str:
    """Extract and verify the JWT from Authorization header or cookie."""
    token: str | None = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email: str | None = payload.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return email
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid JWT: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token")
