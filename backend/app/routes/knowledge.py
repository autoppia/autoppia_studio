import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import httpx

from app.database import (
    companies_collection,
    connectors_collection,
    knowledge_documents_collection,
    tools_collection,
    vector_databases_collection,
)
from app.services.knowledge_index import delete_knowledge_document_vectors
from app.services.queue import enqueue_job

router = APIRouter()

KNOWLEDGE_STORAGE_DIR = Path(os.getenv("KNOWLEDGE_STORAGE_DIR", Path.home() / ".automata" / "knowledge"))
MAX_UPLOAD_BYTES = int(os.getenv("KNOWLEDGE_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".csv", ".json", ".doc", ".docx", ".html", ".xml", ".yml", ".yaml"}


class KnowledgeFromUrlRequest(BaseModel):
    email: str
    companyId: str
    vectorDatabaseId: str = ""
    url: str
    filename: str = ""
    contentType: str = ""
    source: str = "session_artifact"
    metadata: dict = Field(default_factory=dict)


class VectorDatabaseCreateRequest(BaseModel):
    email: str
    companyId: str
    name: str
    provider: str = "local"
    collectionName: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(value: str) -> str:
    name = Path(value or "document").name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(name).stem).strip("-") or "document"
    suffix = Path(name).suffix.lower()
    return f"{stem[:80]}{suffix}"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:80] or "knowledge"


def _filename_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return Path(parsed.path).name or "document"
    except Exception:
        return "document"


def _resource_gate(
    *,
    indexed: bool,
    vector_database_id: str,
    read_tools: list[str],
    acl: dict,
    stale: bool,
    citation_label: str,
) -> dict:
    checks = {
        "indexed": indexed,
        "vectorStore": bool(vector_database_id),
        "readTools": bool(read_tools),
        "acl": bool(acl),
        "freshness": indexed and not stale,
        "citability": indexed and bool(citation_label),
    }
    blockers = [key for key, ready in checks.items() if not ready]
    next_actions: list[str] = []
    if not checks["indexed"]:
        next_actions.append("Wait for indexing to complete or rerun the knowledge indexing job.")
    if not checks["vectorStore"]:
        next_actions.append("Attach the resource to a vector store.")
    if not checks["readTools"]:
        next_actions.append("Expose read-only knowledge tools for this resource store.")
    if not checks["acl"]:
        next_actions.append("Declare ACL visibility, roles or users for the resource.")
    if indexed and stale:
        next_actions.append("Refresh or re-index stale resource content.")
    if indexed and not citation_label:
        next_actions.append("Add a citation label before relying on grounded answers.")
    return {
        "state": "ready" if not blockers else "indexing" if blockers == ["indexed", "freshness", "citability"] else "blocked",
        "readyForRuntime": not blockers,
        "blockers": blockers,
        "nextActions": next_actions,
        "checks": checks,
    }


def _serialize(doc: dict) -> dict:
    resource_id = doc.get("resourceId") or doc.get("documentId", "")
    vector_name = doc.get("vectorDatabaseName", "")
    vector_collection = doc.get("vectorCollectionName", "")
    connector_id = doc.get("connectorId", "")
    indexed = str(doc.get("status") or "").lower() in {"indexed", "ready"}
    created_at = doc.get("createdAt")
    updated_at = doc.get("updatedAt") or created_at
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    version = int(doc.get("version") or metadata.get("version") or 1)
    acl = doc.get("acl") if isinstance(doc.get("acl"), dict) else metadata.get("acl") if isinstance(metadata.get("acl"), dict) else {}
    segment = "_".join(part for part in re.sub(r"[^a-zA-Z0-9]+", "_", str(vector_name or "knowledge").lower()).split("_") if part)[:48] or "knowledge"
    read_tools = [
        f"knowledge.{segment}.search",
        f"knowledge.{segment}.list_documents",
        f"knowledge.{segment}.stats",
        f"knowledge.{segment}.read_document",
    ] if connector_id else []
    stale = bool(doc.get("stale", False))
    citation_label = doc.get("citationLabel") or doc.get("filename", "")
    resource_contract = {
        "resourceId": resource_id,
        "resourceKind": "document",
        "surface": "knowledge_resource",
        "readOnly": True,
        "status": doc.get("status", "uploaded"),
        "indexing": {
            "indexed": indexed,
            "vectorDatabaseId": doc.get("vectorDatabaseId", ""),
            "vectorDatabaseName": vector_name,
            "vectorCollectionName": vector_collection,
        },
        "governance": {
            "companyId": doc.get("companyId", ""),
            "connectorId": connector_id,
            "source": doc.get("source", "upload"),
            "contentType": doc.get("contentType", ""),
            "size": doc.get("size", 0),
            "acl": {
                "visibility": acl.get("visibility") or "company",
                "allowedRoles": acl.get("allowedRoles") if isinstance(acl.get("allowedRoles"), list) else [],
                "allowedUsers": acl.get("allowedUsers") if isinstance(acl.get("allowedUsers"), list) else [],
            },
            "versioning": {
                "version": version,
                "versionLabel": doc.get("versionLabel") or metadata.get("versionLabel") or f"v{version}",
                "createdAt": created_at,
                "updatedAt": updated_at,
            },
            "freshness": {
                "lastIndexedAt": doc.get("lastIndexedAt") or doc.get("indexedAt") or updated_at,
                "stale": stale,
                "status": "current" if indexed and not stale else "stale" if stale else "indexing",
            },
            "citability": {
                "citable": indexed,
                "citationLabel": citation_label,
                "sourceUrl": doc.get("sourceUrl") or metadata.get("sourceUrl") or "",
            },
        },
        "readTools": read_tools,
    }
    resource_contract["resourceGate"] = _resource_gate(
        indexed=indexed,
        vector_database_id=str(doc.get("vectorDatabaseId") or ""),
        read_tools=read_tools,
        acl=acl,
        stale=stale,
        citation_label=str(citation_label or ""),
    )
    return {
        "documentId": doc.get("documentId", ""),
        "resourceId": resource_id,
        "resourceKind": "document",
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "filename": doc.get("filename", ""),
        "contentType": doc.get("contentType", ""),
        "size": doc.get("size", 0),
        "status": doc.get("status", "uploaded"),
        "source": doc.get("source", "upload"),
        "connectorId": doc.get("connectorId", ""),
        "vectorDatabaseId": doc.get("vectorDatabaseId", ""),
        "vectorDatabaseName": doc.get("vectorDatabaseName", ""),
        "vectorCollectionName": doc.get("vectorCollectionName", ""),
        "resourceContract": resource_contract,
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _embedding_payload() -> dict:
    embedding_provider = os.getenv("AUTOMATA_EMBEDDINGS", "hash").strip().lower() or "hash"
    embedding_model = (
        os.getenv("AUTOMATA_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        if embedding_provider == "openai"
        else f"hash-{os.getenv('AUTOMATA_HASH_EMBEDDING_DIMENSIONS', '256')}"
    )
    return {"embeddingProvider": embedding_provider, "embeddingModel": embedding_model}


def _vector_index_payload(company_id: str, connector: dict | None = None, *, documents: list[dict] | None = None) -> dict:
    config = (connector or {}).get("config") if isinstance((connector or {}).get("config"), dict) else {}
    provider = str(config.get("vectorStoreProvider") or os.getenv("AUTOMATA_VECTORSTORE", "local")).strip().lower() or "local"
    collection = str(config.get("collectionName") or f"company-{company_id}")
    embedding = _embedding_payload()
    docs = documents or []
    return {
        "provider": provider,
        "collectionName": collection,
        **embedding,
        "indexedDocuments": sum(1 for doc in docs if str(doc.get("status") or "").lower() in {"indexed", "ready"}),
        "documentCount": len(docs),
    }


def _serialize_vector_database(db: dict, *, documents: list[dict] | None = None, connector: dict | None = None) -> dict:
    docs = documents or []
    embedding = _embedding_payload()
    return {
        "vectorDatabaseId": db.get("vectorDatabaseId", ""),
        "email": db.get("email", ""),
        "companyId": db.get("companyId", ""),
        "name": db.get("name", ""),
        "provider": db.get("provider", "local"),
        "collectionName": db.get("collectionName", ""),
        **embedding,
        "status": db.get("status", "ready"),
        "connectorId": db.get("connectorId") or (connector or {}).get("connectorId", ""),
        "documentCount": len(docs),
        "indexedDocuments": sum(1 for doc in docs if str(doc.get("status") or "").lower() in {"indexed", "ready"}),
        "totalSize": sum(int(doc.get("size") or 0) for doc in docs),
        "createdAt": db.get("createdAt"),
        "updatedAt": db.get("updatedAt"),
    }


async def _ensure_company(email: str, company_id: str) -> None:
    if not await companies_collection.find_one({"email": email, "companyId": company_id}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Company not found")


async def _ensure_default_vector_databases(email: str, company_id: str) -> list[dict]:
    existing = await vector_databases_collection.find({"email": email, "companyId": company_id}, {"_id": 0}).sort("createdAt", 1).to_list(length=100)
    if existing:
        primary = existing[0]
        await knowledge_documents_collection.update_many(
            {"email": email, "companyId": company_id, "vectorDatabaseId": {"$in": [None, ""]}},
            {
                "$set": {
                    "vectorDatabaseId": primary.get("vectorDatabaseId", ""),
                    "vectorDatabaseName": primary.get("name", ""),
                    "vectorCollectionName": primary.get("collectionName", f"company-{company_id}"),
                    "updatedAt": _now(),
                }
            },
        )
        return existing

    now = _now()
    defaults = [
        ("Company Knowledge", f"company-{company_id}-knowledge"),
        ("Product Docs", f"company-{company_id}-product-docs"),
    ]
    docs = []
    for name, collection in defaults:
        doc = {
            "vectorDatabaseId": str(uuid.uuid4()),
            "email": email,
            "companyId": company_id,
            "name": name,
            "provider": os.getenv("AUTOMATA_VECTORSTORE", "local").strip().lower() or "local",
            "collectionName": collection,
            "status": "ready",
            "createdAt": now,
            "updatedAt": now,
        }
        await vector_databases_collection.insert_one(dict(doc))
        docs.append(doc)
    await knowledge_documents_collection.update_many(
        {"email": email, "companyId": company_id, "vectorDatabaseId": {"$in": [None, ""]}},
        {
            "$set": {
                "vectorDatabaseId": docs[0]["vectorDatabaseId"],
                "vectorDatabaseName": docs[0]["name"],
                "vectorCollectionName": docs[0]["collectionName"],
                "updatedAt": now,
            }
        },
    )
    return docs


async def _ensure_vector_database(email: str, company_id: str, vector_database_id: str = "") -> dict:
    await _ensure_default_vector_databases(email, company_id)
    query = {"email": email, "companyId": company_id}
    if vector_database_id:
        query["vectorDatabaseId"] = vector_database_id
    doc = await vector_databases_collection.find_one(query, {"_id": 0}, sort=[("createdAt", 1)])
    if not doc:
        raise HTTPException(status_code=404, detail="Vector database not found")
    return doc


async def _ensure_knowledge_connector(email: str, company_id: str, vector_db: dict | None = None) -> str:
    vector_db = vector_db or await _ensure_vector_database(email, company_id)
    vector_database_id = str(vector_db.get("vectorDatabaseId") or "")
    collection_name = str(vector_db.get("collectionName") or f"company-{company_id}")
    provider = str(vector_db.get("provider") or os.getenv("AUTOMATA_VECTORSTORE", "local")).strip().lower() or "local"
    existing = await connectors_collection.find_one(
        {"email": email, "companyId": company_id, "type": "knowledge", "config.vectorDatabaseId": vector_database_id},
        {"_id": 0},
    )
    if not existing and not vector_database_id:
        existing = await connectors_collection.find_one({"email": email, "companyId": company_id, "type": "knowledge"}, {"_id": 0})
    if existing:
        connector_id = str(existing.get("connectorId") or "")
        config = existing.get("config") if isinstance(existing.get("config"), dict) else {}
        vector_updates = {
            "name": existing.get("name") or f"Documents - {vector_db.get('name', 'Knowledge')}",
            "config.vectorDatabaseId": vector_database_id,
            "config.vectorDatabaseName": vector_db.get("name", ""),
            "config.collectionName": config.get("collectionName") or collection_name,
            "config.vectorStoreProvider": config.get("vectorStoreProvider") or provider,
        }
        if existing.get("status") != "connected":
            vector_updates["status"] = "connected"
        await connectors_collection.update_one(
            {"connectorId": connector_id},
            {"$set": {**vector_updates, "updatedAt": _now()}},
        )
        await _ensure_knowledge_tools(email, company_id, connector_id)
        await vector_databases_collection.update_one(
            {"vectorDatabaseId": vector_database_id},
            {"$set": {"connectorId": connector_id, "updatedAt": _now()}},
        )
        await knowledge_documents_collection.update_many(
            {"email": email, "companyId": company_id, "vectorDatabaseId": vector_database_id},
            {"$set": {"connectorId": connector_id, "updatedAt": _now()}},
        )
        return connector_id

    now = _now()
    connector_id = str(uuid.uuid4())
    name = f"Documents - {vector_db.get('name', 'Knowledge')}"
    await connectors_collection.insert_one(
        {
            "connectorId": connector_id,
            "email": email,
            "companyId": company_id,
            "name": name,
            "type": "knowledge",
            "category": "knowledge",
            "description": f"Knowledge connector bound to the {vector_db.get('name', 'Knowledge')} vector database.",
            "status": "connected",
            "provider": "official",
            "generationStatus": "autoppia_supported",
            "config": {
                "vectorDatabaseId": vector_database_id,
                "vectorDatabaseName": vector_db.get("name", ""),
                "collectionName": collection_name,
                "vectorStoreProvider": provider,
            },
            "createdAt": now,
            "updatedAt": now,
        }
    )
    await _ensure_knowledge_tools(email, company_id, connector_id)
    await vector_databases_collection.update_one(
        {"vectorDatabaseId": vector_database_id},
        {"$set": {"connectorId": connector_id, "updatedAt": now}},
    )
    await knowledge_documents_collection.update_many(
        {"email": email, "companyId": company_id, "vectorDatabaseId": vector_database_id},
        {"$set": {"connectorId": connector_id, "updatedAt": now}},
    )
    return connector_id


async def _ensure_knowledge_tools(email: str, company_id: str, connector_id: str) -> None:
    if not connector_id:
        return
    now = _now()
    connector = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0}) or {}
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    db_name = str(config.get("vectorDatabaseName") or connector.get("name") or "Knowledge")
    tool_segment = "_".join(part for part in re.sub(r"[^a-zA-Z0-9]+", "_", db_name.lower()).split("_") if part)[:48] or "knowledge"
    specs = [
        {
            "name": f"knowledge.{tool_segment}.search",
            "description": f"Search documents indexed in {db_name} using vector similarity and return cited chunks.",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "topK": {"type": "integer"}, "k": {"type": "integer"}, "minScore": {"type": "number"}, "documentId": {"type": "string"}, "source": {"type": "string"}}},
            "outputSchema": {"type": "object", "properties": {"results": {"type": "array"}}},
        },
        {
            "name": f"knowledge.{tool_segment}.list_documents",
            "description": f"List stored documents in {db_name}.",
            "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}},
            "outputSchema": {"type": "object", "properties": {"documents": {"type": "array"}}},
        },
        {
            "name": f"knowledge.{tool_segment}.stats",
            "description": f"Return document and indexing stats for {db_name}.",
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {"type": "object", "additionalProperties": True},
        },
        {
            "name": f"knowledge.{tool_segment}.read_document",
            "description": f"Read a stored {db_name} document by documentId.",
            "inputSchema": {"type": "object", "properties": {"documentId": {"type": "string"}}},
            "outputSchema": {"type": "object", "additionalProperties": True},
        },
    ]
    for spec in specs:
        tool_id = f"{connector_id}:{spec['name']}"
        existing = await tools_collection.find_one({"toolId": tool_id}, {"_id": 0, "createdAt": 1})
        await tools_collection.update_one(
            {"toolId": tool_id},
            {
                "$set": {
                    "toolId": tool_id,
                    "email": email,
                    "companyId": company_id,
                    "connectorId": connector_id,
                    "name": spec["name"],
                    "description": spec["description"],
                    "sideEffects": "reads",
                    "riskLevel": "low",
                    "executionType": "connector_tool",
                    "runtimeRequirements": ["vectorstore", "embedding_model"],
                    "inputSchema": spec["inputSchema"],
                    "outputSchema": spec["outputSchema"],
                    "permissions": {"approval": "never"},
                    "createdAt": existing.get("createdAt") if existing else now,
                    "updatedAt": now,
                }
            },
            upsert=True,
        )


async def create_knowledge_document_record(
    *,
    email: str,
    company_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    source: str,
    vector_database_id: str = "",
    metadata: dict | None = None,
) -> dict:
    await _ensure_company(email, company_id)
    vector_db = await _ensure_vector_database(email, company_id, vector_database_id)
    safe_name = _safe_filename(filename or "document")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        if (content_type or "").lower().startswith("application/pdf"):
            safe_name = f"{Path(safe_name).stem or 'document'}.pdf"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large")

    connector_id = await _ensure_knowledge_connector(email, company_id, vector_db)
    now = _now()
    document_id = str(uuid.uuid4())
    company_dir = KNOWLEDGE_STORAGE_DIR / company_id
    company_dir.mkdir(parents=True, exist_ok=True)
    storage_path = company_dir / f"{document_id}-{safe_name}"
    storage_path.write_bytes(content)

    doc = {
        "documentId": document_id,
        "resourceId": document_id,
        "resourceKind": "document",
        "email": email,
        "companyId": company_id,
        "filename": safe_name,
        "contentType": content_type or "application/octet-stream",
        "size": len(content),
        "status": "indexing",
        "source": source or "upload",
        "connectorId": connector_id,
        "vectorDatabaseId": vector_db.get("vectorDatabaseId", ""),
        "vectorDatabaseName": vector_db.get("name", ""),
        "vectorCollectionName": vector_db.get("collectionName", f"company-{company_id}"),
        "storagePath": str(storage_path),
        "metadata": metadata or {},
        "createdAt": now,
        "updatedAt": now,
    }
    await knowledge_documents_collection.insert_one(dict(doc))
    await enqueue_job("knowledge_index", {"documentId": document_id}, dedupe_key=f"knowledge_index:{document_id}")
    return doc


@router.get("/knowledge/documents")
async def list_knowledge_documents(email: str, companyId: str):
    await _ensure_company(email, companyId)
    vector_dbs = await _ensure_default_vector_databases(email, companyId)
    for vector_db in vector_dbs:
        await _ensure_knowledge_connector(email, companyId, vector_db)
    connectors = await connectors_collection.find({"email": email, "companyId": companyId, "type": "knowledge"}, {"_id": 0}).to_list(length=100)
    connectors_by_db = {
        str((connector.get("config") or {}).get("vectorDatabaseId") or ""): connector
        for connector in connectors
        if isinstance(connector.get("config"), dict)
    }
    cursor = knowledge_documents_collection.find({"email": email, "companyId": companyId}, {"_id": 0, "storagePath": 0}).sort("createdAt", -1)
    docs = await cursor.to_list(length=500)
    primary = vector_dbs[0] if vector_dbs else {}
    primary_docs = [doc for doc in docs if doc.get("vectorDatabaseId") == primary.get("vectorDatabaseId")]
    connector = connectors_by_db.get(str(primary.get("vectorDatabaseId") or ""))
    return {
        "documents": [_serialize(doc) for doc in docs],
        "vectorDatabases": [
            _serialize_vector_database(
                vector_db,
                documents=[doc for doc in docs if doc.get("vectorDatabaseId") == vector_db.get("vectorDatabaseId")],
                connector=connectors_by_db.get(str(vector_db.get("vectorDatabaseId") or "")),
            )
            for vector_db in vector_dbs
        ],
        "vectorIndex": _vector_index_payload(companyId, connector, documents=primary_docs),
    }


@router.post("/knowledge/vector-databases")
async def create_vector_database(body: VectorDatabaseCreateRequest):
    await _ensure_company(body.email, body.companyId)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    now = _now()
    vector_database_id = str(uuid.uuid4())
    collection_name = body.collectionName.strip() or f"company-{body.companyId}-{_safe_slug(name)}"
    doc = {
        "vectorDatabaseId": vector_database_id,
        "email": body.email,
        "companyId": body.companyId,
        "name": name,
        "provider": (body.provider or "local").strip().lower() or "local",
        "collectionName": collection_name,
        "status": "ready",
        "createdAt": now,
        "updatedAt": now,
    }
    await vector_databases_collection.insert_one(dict(doc))
    connector_id = await _ensure_knowledge_connector(body.email, body.companyId, doc)
    doc["connectorId"] = connector_id
    return {"success": True, "vectorDatabase": _serialize_vector_database(doc)}


@router.post("/knowledge/documents")
async def upload_knowledge_document(
    email: str = Form(...),
    companyId: str = Form(...),
    vectorDatabaseId: str = Form(""),
    source: str = Form("upload"),
    file: UploadFile = File(...),
):
    await _ensure_company(email, companyId)
    filename = _safe_filename(file.filename or "document")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large")

    vector_database_id = vectorDatabaseId if isinstance(vectorDatabaseId, str) else ""
    doc = await create_knowledge_document_record(
        email=email,
        company_id=companyId,
        filename=filename,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        source=source or "upload",
        vector_database_id=vector_database_id,
    )
    return {"success": True, "document": _serialize(doc), "connectorId": doc.get("connectorId", "")}


@router.post("/knowledge/documents/from-url")
async def create_knowledge_document_from_url(body: KnowledgeFromUrlRequest):
    await _ensure_company(body.email, body.companyId)
    url = str(body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http(s) URLs can be saved as documents")

    filename = _safe_filename(body.filename or _filename_from_url(url))
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        if (body.contentType or "").lower().startswith("application/pdf"):
            filename = f"{Path(filename).stem or 'document'}.pdf"
            suffix = ".pdf"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not download document: {exc}") from exc

    doc = await create_knowledge_document_record(
        email=body.email,
        company_id=body.companyId,
        filename=filename,
        content=content,
        content_type=body.contentType or response.headers.get("content-type", "application/octet-stream").split(";", 1)[0],
        source=body.source or "session_artifact",
        vector_database_id=body.vectorDatabaseId,
        metadata=body.metadata or {},
    )
    return {"success": True, "document": _serialize(doc), "connectorId": doc.get("connectorId", "")}


@router.delete("/knowledge/documents/{document_id}")
async def delete_knowledge_document(document_id: str):
    doc = await knowledge_documents_collection.find_one({"documentId": document_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    storage_path = doc.get("storagePath")
    if storage_path:
        try:
            Path(storage_path).unlink(missing_ok=True)
        except OSError:
            pass
    await delete_knowledge_document_vectors(str(doc.get("companyId") or ""), document_id, collection=str(doc.get("vectorCollectionName") or ""))
    await knowledge_documents_collection.delete_one({"documentId": document_id})
    return {"success": True}


@router.get("/knowledge/documents/{document_id}/download")
async def download_knowledge_document(document_id: str, email: str, companyId: str):
    await _ensure_company(email, companyId)
    doc = await knowledge_documents_collection.find_one(
        {"documentId": document_id, "email": email, "companyId": companyId},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    storage_path = Path(str(doc.get("storagePath") or ""))
    if not storage_path.exists() or not storage_path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file not found")
    return FileResponse(
        path=str(storage_path),
        media_type=doc.get("contentType") or "application/octet-stream",
        filename=doc.get("filename") or storage_path.name,
    )
