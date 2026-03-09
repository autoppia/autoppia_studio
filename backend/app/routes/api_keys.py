import secrets
import hashlib
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import api_keys_collection

logger = logging.getLogger(__name__)
router = APIRouter()


class APIKeyCreateRequest(BaseModel):
    email: str
    name: str


class APIKeyUpdateRequest(BaseModel):
    name: str


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@router.get("/api-keys")
async def get_api_keys(email: str):
    """Get all API keys for a user (returns masked keys)."""
    try:
        cursor = api_keys_collection.find({"email": email}).sort("createdAt", -1)
        keys = []
        async for doc in cursor:
            keys.append({
                "id": str(doc["_id"]),
                "name": doc["name"],
                "prefix": doc["prefix"],
                "createdAt": doc.get("createdAt"),
            })
        return {"apiKeys": keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api-keys")
async def create_api_key(body: APIKeyCreateRequest):
    """Create a new API key. Returns the full key only once."""
    try:
        raw_key = f"ak_{secrets.token_hex(24)}"
        prefix = raw_key[:10] + "..."
        key_hash = _hash_key(raw_key)

        now = datetime.now(timezone.utc)
        doc = {
            "email": body.email,
            "name": body.name,
            "keyHash": key_hash,
            "prefix": prefix,
            "createdAt": now,
        }
        result = await api_keys_collection.insert_one(doc)
        return {
            "success": True,
            "apiKey": {
                "id": str(result.inserted_id),
                "name": body.name,
                "prefix": prefix,
                "key": raw_key,
                "createdAt": now,
            },
        }
    except Exception as e:
        logger.error(f"Failed to create API key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api-keys/{key_id}")
async def update_api_key(key_id: str, body: APIKeyUpdateRequest):
    """Rename an API key."""
    try:
        result = await api_keys_collection.update_one(
            {"_id": ObjectId(key_id)},
            {"$set": {"name": body.name}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="API key not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str):
    """Delete an API key."""
    try:
        result = await api_keys_collection.delete_one({"_id": ObjectId(key_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="API key not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
