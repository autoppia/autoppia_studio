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

from app.database import companies_collection, connectors_collection, knowledge_documents_collection

router = APIRouter()

KNOWLEDGE_STORAGE_DIR = Path(os.getenv("KNOWLEDGE_STORAGE_DIR", Path.home() / ".automata" / "knowledge"))
MAX_UPLOAD_BYTES = int(os.getenv("KNOWLEDGE_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".csv", ".json", ".doc", ".docx"}


class KnowledgeFromUrlRequest(BaseModel):
    email: str
    companyId: str
    url: str
    filename: str = ""
    contentType: str = ""
    source: str = "session_artifact"
    metadata: dict = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(value: str) -> str:
    name = Path(value or "document").name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(name).stem).strip("-") or "document"
    suffix = Path(name).suffix.lower()
    return f"{stem[:80]}{suffix}"


def _filename_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return Path(parsed.path).name or "document"
    except Exception:
        return "document"


def _serialize(doc: dict) -> dict:
    return {
        "documentId": doc.get("documentId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "filename": doc.get("filename", ""),
        "contentType": doc.get("contentType", ""),
        "size": doc.get("size", 0),
        "status": doc.get("status", "uploaded"),
        "source": doc.get("source", "upload"),
        "connectorId": doc.get("connectorId", ""),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _ensure_company(email: str, company_id: str) -> None:
    if not await companies_collection.find_one({"email": email, "companyId": company_id}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Company not found")


async def _ensure_knowledge_connector(email: str, company_id: str) -> str:
    existing = await connectors_collection.find_one({"email": email, "companyId": company_id, "type": "knowledge"}, {"_id": 0})
    if existing:
        if existing.get("status") != "connected":
            await connectors_collection.update_one(
                {"connectorId": existing.get("connectorId")},
                {"$set": {"status": "connected", "updatedAt": _now()}},
            )
        return str(existing.get("connectorId") or "")

    now = _now()
    connector_id = str(uuid.uuid4())
    await connectors_collection.insert_one(
        {
            "connectorId": connector_id,
            "email": email,
            "companyId": company_id,
            "name": "Documents",
            "type": "knowledge",
            "category": "knowledge",
            "description": "Company knowledge connector for uploaded documents and internal sources.",
            "status": "connected",
            "provider": "official",
            "generationStatus": "autoppia_supported",
            "config": {"collectionName": f"company-{company_id}"},
            "createdAt": now,
            "updatedAt": now,
        }
    )
    return connector_id


async def create_knowledge_document_record(
    *,
    email: str,
    company_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    source: str,
    metadata: dict | None = None,
) -> dict:
    await _ensure_company(email, company_id)
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

    connector_id = await _ensure_knowledge_connector(email, company_id)
    now = _now()
    document_id = str(uuid.uuid4())
    company_dir = KNOWLEDGE_STORAGE_DIR / company_id
    company_dir.mkdir(parents=True, exist_ok=True)
    storage_path = company_dir / f"{document_id}-{safe_name}"
    storage_path.write_bytes(content)

    doc = {
        "documentId": document_id,
        "email": email,
        "companyId": company_id,
        "filename": safe_name,
        "contentType": content_type or "application/octet-stream",
        "size": len(content),
        "status": "uploaded",
        "source": source or "upload",
        "connectorId": connector_id,
        "storagePath": str(storage_path),
        "metadata": metadata or {},
        "createdAt": now,
        "updatedAt": now,
    }
    await knowledge_documents_collection.insert_one(dict(doc))
    return doc


@router.get("/knowledge/documents")
async def list_knowledge_documents(email: str, companyId: str):
    await _ensure_company(email, companyId)
    cursor = knowledge_documents_collection.find({"email": email, "companyId": companyId}, {"_id": 0, "storagePath": 0}).sort("createdAt", -1)
    return {"documents": [_serialize(doc) async for doc in cursor]}


@router.post("/knowledge/documents")
async def upload_knowledge_document(
    email: str = Form(...),
    companyId: str = Form(...),
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

    doc = await create_knowledge_document_record(
        email=email,
        company_id=companyId,
        filename=filename,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        source=source or "upload",
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
