from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routes import knowledge as knowledge_route


class _Result:
    matched_count = 1


class _FakeCompaniesCollection:
    async def find_one(self, query, projection=None):
        if query.get("email") == "user@example.com" and query.get("companyId") == "company-1":
            return {"companyId": "company-1"}
        return None


class _FakeConnectorsCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update["$set"])
        return _Result()


class _FakeDocumentsCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _UploadFile:
    filename = "handbook.md"
    content_type = "text/markdown"

    async def read(self):
        return b"# Handbook"


@pytest.mark.asyncio
async def test_upload_document_creates_knowledge_connector(monkeypatch, tmp_path):
    connectors = _FakeConnectorsCollection()
    documents = _FakeDocumentsCollection()
    monkeypatch.setattr(knowledge_route, "companies_collection", _FakeCompaniesCollection())
    monkeypatch.setattr(knowledge_route, "connectors_collection", connectors)
    monkeypatch.setattr(knowledge_route, "knowledge_documents_collection", documents)
    monkeypatch.setattr(knowledge_route, "KNOWLEDGE_STORAGE_DIR", tmp_path)

    result = await knowledge_route.upload_knowledge_document(
        email="user@example.com",
        companyId="company-1",
        source="test",
        file=_UploadFile(),
    )

    assert result["success"] is True
    assert result["document"]["filename"] == "handbook.md"
    assert result["document"]["status"] == "uploaded"
    assert connectors.docs[0]["type"] == "knowledge"
    assert documents.docs[0]["connectorId"] == connectors.docs[0]["connectorId"]
    assert Path(documents.docs[0]["storagePath"]).exists()


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_file_type(monkeypatch):
    monkeypatch.setattr(knowledge_route, "companies_collection", _FakeCompaniesCollection())

    class BadUpload:
        filename = "malware.exe"
        content_type = "application/octet-stream"

        async def read(self):
            return b"data"

    with pytest.raises(HTTPException) as exc:
        await knowledge_route.upload_knowledge_document(
            email="user@example.com",
            companyId="company-1",
            source="test",
            file=BadUpload(),
        )

    assert exc.value.status_code == 400
