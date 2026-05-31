import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import companies_collection

router = APIRouter()


class CompanyCreateRequest(BaseModel):
    email: str
    name: str
    description: str = ""
    industry: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "description": doc.get("description", ""),
        "industry": doc.get("industry", ""),
        "status": doc.get("status", "active"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _ensure_default_company(email: str) -> dict[str, Any]:
    existing = await companies_collection.find_one({"email": email})
    if existing:
        return existing
    now = _now()
    doc = {
        "companyId": str(uuid.uuid4()),
        "email": email,
        "name": "Default Company",
        "description": "Default workspace for agents, integrations, skills, benchmarks, and runs.",
        "industry": "",
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }
    await companies_collection.insert_one(doc)
    return doc


@router.get("/companies")
async def list_companies(email: str):
    try:
        await _ensure_default_company(email)
        cursor = companies_collection.find({"email": email}, {"_id": 0}).sort("createdAt", 1)
        return {"companies": [_serialize(doc) async for doc in cursor]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/companies")
async def create_company(body: CompanyCreateRequest):
    try:
        now = _now()
        doc = {
            "companyId": str(uuid.uuid4()),
            "email": body.email,
            "name": body.name.strip() or "Untitled Company",
            "description": body.description.strip(),
            "industry": body.industry.strip(),
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        await companies_collection.insert_one(doc)
        return {"success": True, "company": _serialize(doc)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
