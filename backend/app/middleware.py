import hashlib

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.api_errors import error_payload
from app.database import api_keys_collection

api_key_header = APIKeyHeader(name="x-api-key")


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(api_key: str = Security(api_key_header)):
    key_hash = _hash_key(api_key)
    doc = await api_keys_collection.find_one({"keyHash": key_hash})
    if not doc:
        raise HTTPException(
            status_code=401,
            detail=error_payload("invalid_api_key", "Invalid API key"),
        )
    return doc
