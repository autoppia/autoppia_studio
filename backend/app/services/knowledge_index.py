from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.services.vectorstore.base import VectorChunk
from app.services.vectorstore.embeddings import get_embedding_model
from app.services.vectorstore.factory import get_vectorstore


def collection_name(company_id: str) -> str:
    return f"company-{company_id}"


def document_collection_name(doc: dict[str, Any]) -> str:
    return str(doc.get("vectorCollectionName") or collection_name(str(doc.get("companyId") or "")))


def extract_text(path: str, content_type: str = "") -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json"} or content_type.startswith("text/"):
        return file_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        return _extract_pdf_text(file_path)
    if suffix == ".docx":
        return _extract_docx_text(file_path)
    if suffix == ".doc":
        return file_path.read_bytes().decode("utf-8", errors="ignore")
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text

        return str(pdfminer_extract_text(str(path)) or "")
    except Exception:
        return path.read_bytes().decode("utf-8", errors="ignore")


def _extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        parts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
        return "\n".join(part for part in parts if part.strip())
    except Exception:
        return path.read_bytes().decode("utf-8", errors="ignore")


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 180) -> list[str]:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return []
    chunks = []
    start = 0
    chunk_size = max(200, int(chunk_size or 1200))
    overlap = max(0, min(int(overlap or 0), chunk_size // 2))
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return chunks


async def index_knowledge_document(doc: dict[str, Any]) -> dict[str, Any]:
    text = extract_text(str(doc.get("storagePath") or ""), str(doc.get("contentType") or ""))
    chunks = chunk_text(text)
    embeddings = await get_embedding_model().embed(chunks) if chunks else []
    vector_chunks = [
        VectorChunk(
            id=f"{doc.get('documentId')}:{idx}",
            document_id=str(doc.get("documentId") or ""),
            text=chunk,
            embedding=embeddings[idx],
            metadata={
                "companyId": doc.get("companyId", ""),
                "email": doc.get("email", ""),
                "documentId": doc.get("documentId", ""),
                "vectorDatabaseId": doc.get("vectorDatabaseId", ""),
                "vectorDatabaseName": doc.get("vectorDatabaseName", ""),
                "filename": doc.get("filename", ""),
                "chunkIndex": idx,
                "source": doc.get("source", ""),
            },
        )
        for idx, chunk in enumerate(chunks)
    ]
    collection = document_collection_name(doc)
    await get_vectorstore().delete(collection, str(doc.get("documentId") or ""))
    if vector_chunks:
        await get_vectorstore().upsert(collection, vector_chunks)
    return {"chunkCount": len(vector_chunks), "textLength": len(text)}


async def delete_knowledge_document_vectors(company_id: str, document_id: str, *, collection: str = "") -> None:
    await get_vectorstore().delete(collection or collection_name(company_id), document_id)


async def search_knowledge(
    *,
    company_id: str,
    query: str,
    k: int = 5,
    collection: str = "",
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    embeddings = await get_embedding_model().embed([query])
    hits = await get_vectorstore().query(collection or collection_name(company_id), embeddings[0], k=k, filters=filters or {})
    return [
        {
            "chunkId": hit.id,
            "documentId": hit.document_id,
            "score": hit.score,
            "text": hit.text,
            "snippet": hit.text[:700],
            "metadata": hit.metadata,
            "citation": {
                "documentId": hit.document_id,
                "filename": hit.metadata.get("filename", ""),
                "chunkIndex": hit.metadata.get("chunkIndex", 0),
            },
        }
        for hit in hits
    ]
