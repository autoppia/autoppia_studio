from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.database import companies_collection, connectors_collection, entities_collection
from app.models.entity import EntityField, EntityRelationship
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.services.entity_mapper import propose_entities_from_openapi_url

router = APIRouter()


class EntityCreateRequest(BaseModel):
    email: str
    name: str
    description: str = ""
    fields: list[EntityField] = Field(default_factory=list)
    relationships: list[EntityRelationship] = Field(default_factory=list)
    sourceConnectorId: str = ""
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = _clean_entity_name(value)
        if not name:
            raise ValueError("name is required")
        return name


class EntityUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[EntityField] | None = None
    relationships: list[EntityRelationship] | None = None
    sourceConnectorId: str | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = _clean_entity_name(value)
        if not name:
            raise ValueError("name is required")
        return name


class EntityGenerateRequest(BaseModel):
    email: str
    sourceUrl: str = ""
    apply: bool = False
    replaceExisting: bool = False
    sourceConnectorId: str = ""
    limit: int = Field(default=25, ge=1, le=100)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_entity_name(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    return compact[:80]


def _serialize_entity(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "entityId": doc.get("entityId", ""),
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "description": doc.get("description", ""),
        "fields": doc.get("fields") if isinstance(doc.get("fields"), list) else [],
        "relationships": doc.get("relationships") if isinstance(doc.get("relationships"), list) else [],
        "sourceConnectorId": doc.get("sourceConnectorId", ""),
        "source": doc.get("source", "manual"),
        "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _ensure_company(company_id: str, scope: RequestScope | None = None) -> dict[str, Any]:
    scope = coerce_request_scope(scope)
    query: dict[str, Any] = {"companyId": company_id}
    if scope and scope.email:
        query["email"] = scope.email
    company = await companies_collection.find_one(query, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def _owned_entity(entity_id: str, scope: RequestScope | None = None) -> dict[str, Any]:
    scope = coerce_request_scope(scope)
    query: dict[str, Any] = {"entityId": entity_id}
    if scope and scope.email:
        query["email"] = scope.email
    doc = await entities_collection.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Entity not found")
    return doc


async def _resolve_entity_generation_source(company_id: str, email: str, body: EntityGenerateRequest) -> tuple[str, str]:
    source_url = body.sourceUrl.strip()
    connector_id = body.sourceConnectorId.strip()
    if source_url:
        return source_url, connector_id
    if not connector_id:
        raise HTTPException(status_code=400, detail="sourceUrl or sourceConnectorId is required")
    connector = await connectors_collection.find_one(
        {"companyId": company_id, "email": email, "connectorId": connector_id},
        {"_id": 0},
    )
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    for key in ("openApiUrl", "docsUrl", "sourceUrl"):
        candidate = str(config.get(key) or "").strip()
        if candidate:
            return candidate, connector_id
    raise HTTPException(status_code=400, detail="Connector has no OpenAPI or documentation URL")


def _relationship_edges(entity: dict[str, Any]) -> list[dict[str, Any]]:
    source = str(entity.get("name") or "")
    edges = []
    for rel in entity.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        target = str(rel.get("target") or "").strip()
        if not source or not target:
            continue
        edges.append(
            {
                "from": source,
                "to": target,
                "name": rel.get("name", ""),
                "kind": rel.get("kind", "references"),
                "via": rel.get("via", ""),
                "description": rel.get("description", ""),
            }
        )
    return edges


@router.get("/companies/{company_id}/entities")
async def list_company_entities(company_id: str, email: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(email)
    await _ensure_company(company_id, scope)
    cursor = entities_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).sort("name", 1)
    return {"entities": [_serialize_entity(doc) async for doc in cursor]}


@router.post("/companies/{company_id}/entities")
async def create_company_entity(company_id: str, body: EntityCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    await _ensure_company(company_id, scope)
    if await entities_collection.find_one({"companyId": company_id, "name": body.name}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Entity name already exists for this company")
    now = _now()
    doc = {
        "entityId": str(uuid.uuid4()),
        "companyId": company_id,
        "email": email,
        "name": body.name,
        "description": body.description.strip(),
        "fields": [field.model_dump() for field in body.fields],
        "relationships": [rel.model_dump() for rel in body.relationships],
        "sourceConnectorId": body.sourceConnectorId,
        "source": body.source or "manual",
        "metadata": body.metadata,
        "createdAt": now,
        "updatedAt": now,
    }
    await entities_collection.insert_one(doc)
    return {"success": True, "entity": _serialize_entity(doc)}


@router.post("/companies/{company_id}/entities/generate")
async def generate_company_entities(company_id: str, body: EntityGenerateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    await _ensure_company(company_id, scope)
    source_url, source_connector_id = await _resolve_entity_generation_source(company_id, email, body)
    proposals = (await propose_entities_from_openapi_url(source_url))[: body.limit]
    existing = await entities_collection.find({"companyId": company_id, "email": email}, {"_id": 0, "name": 1}).to_list(length=500)
    existing_names = {str(doc.get("name") or "") for doc in existing}
    generated = []
    skipped = []
    now = _now()

    for proposal in proposals:
        name = _clean_entity_name(str(proposal.get("name") or ""))
        if not name:
            continue
        doc = {
            "entityId": str(uuid.uuid4()),
            "companyId": company_id,
            "email": email,
            "name": name,
            "description": str(proposal.get("description") or "").strip(),
            "fields": proposal.get("fields") if isinstance(proposal.get("fields"), list) else [],
            "relationships": proposal.get("relationships") if isinstance(proposal.get("relationships"), list) else [],
            "sourceConnectorId": source_connector_id,
            "source": "openapi",
            "metadata": {
                **(proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {}),
                "sourceUrl": source_url,
                **({"sourceConnectorId": source_connector_id} if source_connector_id else {}),
            },
            "createdAt": now,
            "updatedAt": now,
        }
        if not body.apply:
            generated.append(_serialize_entity(doc))
            continue
        if name in existing_names and not body.replaceExisting:
            skipped.append({"name": name, "reason": "already_exists"})
            continue
        if name in existing_names and body.replaceExisting:
            await entities_collection.update_one(
                {"companyId": company_id, "email": email, "name": name},
                {"$set": {key: value for key, value in doc.items() if key not in {"entityId", "createdAt"}}},
            )
            refreshed = await entities_collection.find_one({"companyId": company_id, "email": email, "name": name}, {"_id": 0}) or doc
            generated.append(_serialize_entity(refreshed))
            continue
        await entities_collection.insert_one(doc)
        existing_names.add(name)
        generated.append(_serialize_entity(doc))

    return {
        "success": True,
        "applied": body.apply,
        "entities": generated,
        "skipped": skipped,
        "sourceUrl": source_url,
        "sourceConnectorId": source_connector_id,
    }


@router.patch("/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    existing = await _owned_entity(entity_id, scope)
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if "description" in updates:
        updates["description"] = str(updates["description"]).strip()
    if "fields" in updates:
        updates["fields"] = [field.model_dump() if hasattr(field, "model_dump") else field for field in updates["fields"]]
    if "relationships" in updates:
        updates["relationships"] = [rel.model_dump() if hasattr(rel, "model_dump") else rel for rel in updates["relationships"]]
    if "name" in updates and updates["name"] != existing.get("name"):
        duplicate = await entities_collection.find_one({"companyId": existing.get("companyId", ""), "name": updates["name"], "entityId": {"$ne": entity_id}}, {"_id": 1})
        if duplicate:
            raise HTTPException(status_code=409, detail="Entity name already exists for this company")
    updates["updatedAt"] = _now()
    await entities_collection.update_one({"entityId": entity_id, "email": existing.get("email", "")}, {"$set": updates})
    refreshed = await entities_collection.find_one({"entityId": entity_id}, {"_id": 0})
    return {"success": True, "entity": _serialize_entity(refreshed or {**existing, **updates})}


@router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: str, scope: RequestScope = Depends(get_request_scope)):
    existing = await _owned_entity(entity_id, scope)
    result = await entities_collection.delete_one({"entityId": entity_id, "email": existing.get("email", "")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"success": True}


@router.get("/companies/{company_id}/entities/graph")
async def company_entity_graph(company_id: str, email: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(email)
    await _ensure_company(company_id, scope)
    docs = await entities_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).sort("name", 1).to_list(length=500)
    nodes = [
        {
            "id": doc.get("name", ""),
            "entityId": doc.get("entityId", ""),
            "name": doc.get("name", ""),
            "description": doc.get("description", ""),
            "fieldCount": len(doc.get("fields") or []),
            "sourceConnectorId": doc.get("sourceConnectorId", ""),
            "source": doc.get("source", "manual"),
        }
        for doc in docs
    ]
    edges = [edge for doc in docs for edge in _relationship_edges(doc)]
    return {"nodes": nodes, "edges": edges, "entities": [_serialize_entity(doc) for doc in docs]}
