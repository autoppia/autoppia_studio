import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import companies_collection
from app.database import (
    capabilities_collection,
    eval_runs_collection,
    evals_collection,
    operator_webs_collection,
    operators_collection,
    trajectories_collection,
)

router = APIRouter()


class CompanyCreateRequest(BaseModel):
    email: str
    name: str
    description: str = ""
    industry: str = ""


class CompanyUpdateRequest(BaseModel):
    name: str
    description: str = ""
    industry: str = ""


class DemoResetRequest(BaseModel):
    email: str


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


@router.put("/companies/{company_id}")
async def update_company(company_id: str, body: CompanyUpdateRequest):
    try:
        now = _now()
        update = {
            "name": body.name.strip() or "Untitled Company",
            "description": body.description.strip(),
            "industry": body.industry.strip(),
            "updatedAt": now,
        }
        result = await companies_collection.update_one({"companyId": company_id}, {"$set": update})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Company not found")
        doc = await companies_collection.find_one({"companyId": company_id}, {"_id": 0})
        return {"success": True, "company": _serialize(doc or {"companyId": company_id, **update})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str):
    try:
        company = await companies_collection.find_one({"companyId": company_id}, {"_id": 0})
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        operator_docs = await operators_collection.find(
            {"companyId": company_id},
            {"_id": 0, "operatorId": 1},
        ).to_list(length=500)
        operator_ids = [doc.get("operatorId") for doc in operator_docs if doc.get("operatorId")]
        if operator_ids:
            await operator_webs_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await trajectories_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await capabilities_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await evals_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await eval_runs_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await operators_collection.delete_many({"operatorId": {"$in": operator_ids}})
        await companies_collection.delete_one({"companyId": company_id})
        await _ensure_default_company(str(company.get("email") or ""))
        return {"success": True, "deletedOperators": len(operator_ids)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/demo/celeris/reset")
async def reset_celeris_demo(body: DemoResetRequest):
    try:
        operator_docs = await operators_collection.find(
            {"email": body.email, "name": {"$regex": "celer[ií]s|celeris", "$options": "i"}},
            {"_id": 0, "operatorId": 1},
        ).to_list(length=100)
        operator_ids = [doc.get("operatorId") for doc in operator_docs if doc.get("operatorId")]
        if operator_ids:
            await operator_webs_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await trajectories_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await capabilities_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await evals_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await eval_runs_collection.delete_many({"operatorId": {"$in": operator_ids}})
            await operators_collection.delete_many({"operatorId": {"$in": operator_ids}})
        await companies_collection.delete_many(
            {"email": body.email, "name": {"$regex": "celer[ií]s|celeris", "$options": "i"}}
        )
        return {"success": True, "deletedOperators": len(operator_ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
