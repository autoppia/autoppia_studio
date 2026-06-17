import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import credentials_collection
from app.repositories import CredentialRepository
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope

router = APIRouter()


class CredentialCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    name: str
    value: str
    type: str = "token"
    createdFor: str = "connector"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialUpdateRequest(BaseModel):
    name: str | None = None
    value: str | None = None
    metadata: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet() -> Fernet:
    explicit = (os.getenv("AUTOMATA_CREDENTIALS_KEY") or "").strip()
    if explicit:
        return Fernet(explicit.encode("utf-8"))
    seed = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or "automata-local-dev-credentials-key"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(str(value or "").encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(str(value or "").encode("utf-8")).decode("utf-8")


def mask_secret(value: str | None) -> str:
    if value is None:
        return ""
    raw = str(value)
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:3]}{'*' * max(4, len(raw) - 6)}{raw[-3:]}"


def secret_ref_for(credential_id: str) -> str:
    return f"secret://credential/{credential_id}"


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    encrypted = str(doc.get("encryptedValue") or "")
    try:
        masked = mask_secret(decrypt_secret(encrypted)) if encrypted else ""
    except Exception:
        masked = "********"
    return {
        "credentialId": doc.get("credentialId", ""),
        "secretRef": doc.get("secretRef", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "name": doc.get("name", ""),
        "type": doc.get("type", "token"),
        "createdFor": doc.get("createdFor", "connector"),
        "metadata": doc.get("metadata", {}),
        "configured": bool(encrypted),
        "maskedValue": masked,
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def create_credential_record(
    *,
    email: str,
    company_id: str,
    name: str,
    value: str,
    credential_type: str = "token",
    created_for: str = "connector",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    credential_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "credentialId": credential_id,
        "secretRef": secret_ref_for(credential_id),
        "email": email,
        "companyId": company_id,
        "name": name.strip() or "Credential",
        "type": credential_type or "token",
        "createdFor": created_for or "connector",
        "encryptedValue": encrypt_secret(value),
        "metadata": metadata or {},
        "createdAt": now,
        "updatedAt": now,
    }
    await credentials_collection.insert_one(doc)
    return doc


async def resolve_secret_refs(secret_refs: dict[str, str]) -> dict[str, str]:
    refs = [ref for ref in secret_refs.values() if ref]
    if not refs:
        return {}
    cursor = credentials_collection.find({"secretRef": {"$in": refs}}, {"_id": 0})
    by_ref = {doc["secretRef"]: doc async for doc in cursor}
    resolved: dict[str, str] = {}
    for field, ref in secret_refs.items():
        doc = by_ref.get(ref)
        if not doc:
            continue
        resolved[field] = decrypt_secret(str(doc.get("encryptedValue") or ""))
    return resolved


def _repo(scope: RequestScope) -> CredentialRepository:
    scope = coerce_request_scope(scope)
    return CredentialRepository(credentials_collection, scope)


@router.get("/credentials")
async def list_credentials(email: str, companyId: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    query: dict[str, Any] = {"email": scope.require_email(email)}
    if companyId:
        query["companyId"] = companyId
    cursor = credentials_collection.find(query, {"_id": 0}).sort("createdAt", -1)
    return {"credentials": [_serialize(doc) async for doc in cursor]}


@router.post("/credentials")
async def create_credential(body: CredentialCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    doc = await create_credential_record(
        email=email,
        company_id=body.companyId,
        name=body.name,
        value=body.value,
        credential_type=body.type,
        created_for=body.createdFor,
        metadata=body.metadata,
    )
    return {"success": True, "credential": _serialize(doc)}


@router.patch("/credentials/{credential_id}")
async def update_credential(credential_id: str, body: CredentialUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    repo = _repo(scope)
    existing = await repo.by_id(credential_id)
    update: dict[str, Any] = {"updatedAt": _now()}
    if body.name is not None:
        update["name"] = body.name.strip() or existing.get("name", "Credential")
    if body.value is not None:
        update["encryptedValue"] = encrypt_secret(body.value)
    if body.metadata is not None:
        update["metadata"] = body.metadata
    doc = await repo.update_owned_one({"credentialId": credential_id}, {"$set": update}, not_found="Credential not found")
    return {"success": True, "credential": _serialize(doc or {**existing, **update})}


@router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: str, scope: RequestScope = Depends(get_request_scope)):
    deleted = await _repo(scope).delete_owned_one({"credentialId": credential_id}, not_found="Credential not found")
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"success": True}
