from pathlib import Path

import pytest
from fastapi import HTTPException

from app.connectors.base import ConnectorConfig
from app.connectors.implementations import KnowledgeConnector
from app.routes import knowledge as knowledge_route
from app.services import knowledge_index
from app.services.vectorstore.local_store import LocalJsonVectorStore


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

    async def find_one(self, query, projection=None, **kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update["$set"])
                return _Result()
        if upsert:
            doc = dict(query)
            doc.update(update.get("$set", {}))
            self.docs.append(doc)
        return _Result()

    def find(self, query, projection=None):
        docs = [dict(doc) for doc in self.docs if all(doc.get(key) == value for key, value in query.items())]
        return _FakeCursor(docs)


class _FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args):
        return self

    async def to_list(self, length=100):
        return [dict(doc) for doc in self.docs[:length]]


class _FakeDocumentsCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return _Result()
        return _Result()

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    if doc.get(key) not in value["$in"]:
                        matched = False
                        break
                elif doc.get(key) != value:
                    matched = False
                    break
            if matched:
                doc.update(update.get("$set", {}))
                count += 1
        result = _Result()
        result.matched_count = count
        return result

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                row = dict(doc)
                if projection and projection.get("storagePath") == 0:
                    row.pop("storagePath", None)
                docs.append(row)
        return _FakeCursor(docs)


class _FakeToolsCollection(_FakeConnectorsCollection):
    pass


class _FakeVectorDatabasesCollection(_FakeConnectorsCollection):
    def find(self, query, projection=None):
        docs = [dict(doc) for doc in self.docs if all(doc.get(key) == value for key, value in query.items())]
        return _FakeCursor(docs)


class _UploadFile:
    filename = "handbook.md"
    content_type = "text/markdown"

    async def read(self):
        return b"# Handbook"


@pytest.mark.asyncio
async def test_upload_document_creates_knowledge_connector(monkeypatch, tmp_path):
    connectors = _FakeConnectorsCollection()
    documents = _FakeDocumentsCollection()
    tools = _FakeToolsCollection()
    vector_dbs = _FakeVectorDatabasesCollection()
    monkeypatch.setattr(knowledge_route, "companies_collection", _FakeCompaniesCollection())
    monkeypatch.setattr(knowledge_route, "connectors_collection", connectors)
    monkeypatch.setattr(knowledge_route, "knowledge_documents_collection", documents)
    monkeypatch.setattr(knowledge_route, "tools_collection", tools)
    monkeypatch.setattr(knowledge_route, "vector_databases_collection", vector_dbs)
    monkeypatch.setattr(knowledge_route, "KNOWLEDGE_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(knowledge_index, "get_vectorstore", lambda: LocalJsonVectorStore(tmp_path / "vectors"))
    jobs = []

    async def fake_enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    monkeypatch.setattr(knowledge_route, "enqueue_job", fake_enqueue_job)

    result = await knowledge_route.upload_knowledge_document(
        email="user@example.com",
        companyId="company-1",
        source="test",
        file=_UploadFile(),
    )

    assert result["success"] is True
    assert result["document"]["filename"] == "handbook.md"
    assert result["document"]["status"] == "indexing"
    assert result["document"]["resourceId"] == result["document"]["documentId"]
    assert result["document"]["resourceKind"] == "document"
    assert result["document"]["resourceContract"]["surface"] == "knowledge_resource"
    assert result["document"]["resourceContract"]["readOnly"] is True
    assert result["document"]["resourceContract"]["indexing"]["vectorDatabaseId"] == vector_dbs.docs[0]["vectorDatabaseId"]
    assert result["document"]["resourceContract"]["governance"]["acl"]["visibility"] == "company"
    assert result["document"]["resourceContract"]["governance"]["versioning"]["version"] == 1
    assert result["document"]["resourceContract"]["governance"]["freshness"]["status"] == "indexing"
    assert result["document"]["resourceContract"]["governance"]["citability"]["citable"] is False
    assert result["document"]["resourceContract"]["governance"]["citability"]["citationLabel"] == "handbook.md"
    assert "knowledge.company_knowledge.search" in result["document"]["resourceContract"]["readTools"]
    assert len(vector_dbs.docs) == 2
    assert connectors.docs[0]["type"] == "knowledge"
    assert documents.docs[0]["connectorId"] == connectors.docs[0]["connectorId"]
    assert documents.docs[0]["vectorDatabaseId"] == vector_dbs.docs[0]["vectorDatabaseId"]
    assert {tool["name"] for tool in tools.docs} == {
        "knowledge.company_knowledge.search",
        "knowledge.company_knowledge.list_documents",
        "knowledge.company_knowledge.stats",
        "knowledge.company_knowledge.read_document",
    }
    assert all(tool["companyId"] == "company-1" for tool in tools.docs)
    assert jobs[0][0] == "knowledge_index"
    assert jobs[0][1]["documentId"] == documents.docs[0]["documentId"]
    assert Path(documents.docs[0]["storagePath"]).exists()


@pytest.mark.asyncio
async def test_knowledge_search_uses_vectorstore(monkeypatch, tmp_path):
    connectors = _FakeConnectorsCollection()
    documents = _FakeDocumentsCollection()
    tools = _FakeToolsCollection()
    vector_dbs = _FakeVectorDatabasesCollection()
    monkeypatch.setattr(knowledge_route, "companies_collection", _FakeCompaniesCollection())
    monkeypatch.setattr(knowledge_route, "connectors_collection", connectors)
    monkeypatch.setattr(knowledge_route, "knowledge_documents_collection", documents)
    monkeypatch.setattr(knowledge_route, "tools_collection", tools)
    monkeypatch.setattr(knowledge_route, "vector_databases_collection", vector_dbs)
    monkeypatch.setattr("app.connectors.implementations.knowledge_documents_collection", documents)
    monkeypatch.setattr(knowledge_route, "KNOWLEDGE_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(knowledge_index, "get_vectorstore", lambda: LocalJsonVectorStore(tmp_path / "vectors"))
    async def fake_enqueue_job(job_type, payload, **kwargs):
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    monkeypatch.setattr(knowledge_route, "enqueue_job", fake_enqueue_job)

    class SearchUpload:
        filename = "policies.md"
        content_type = "text/markdown"

        async def read(self):
            return b"Policy renewals happen in March. Customer reminders should include premium and due date."

    uploaded = await knowledge_route.upload_knowledge_document(
        email="user@example.com",
        companyId="company-1",
        source="test",
        file=SearchUpload(),
    )
    await knowledge_index.index_knowledge_document(documents.docs[0])
    connector = KnowledgeConnector(
        ConnectorConfig(
            connector_id=uploaded["connectorId"],
            company_id="company-1",
            email="user@example.com",
            name="Documents",
            type="knowledge",
            status="connected",
            config={
                "vectorDatabaseId": documents.docs[0]["vectorDatabaseId"],
                "collectionName": documents.docs[0]["vectorCollectionName"],
            },
        )
    )

    result = await connector.execute("knowledge.search", {"query": "renewal reminder premium", "k": 3})

    assert result.success is True
    assert result.output["results"][0]["documentId"] == uploaded["document"]["documentId"]
    assert "premium" in result.output["results"][0]["snippet"].lower()

    listed = await connector.execute("knowledge.company_knowledge.list_documents", {"limit": 10})
    stats = await connector.execute("knowledge.company_knowledge.stats", {})

    assert listed.output["count"] == 1
    assert listed.output["documents"][0]["documentId"] == uploaded["document"]["documentId"]
    assert stats.output["documentCount"] == 1
    assert stats.output["indexedDocuments"] == 0


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


def test_vector_index_payload_names_provider_collection_and_embedding(monkeypatch):
    monkeypatch.setenv("AUTOMATA_VECTORSTORE", "chroma")
    monkeypatch.setenv("AUTOMATA_EMBEDDINGS", "hash")
    monkeypatch.setenv("AUTOMATA_HASH_EMBEDDING_DIMENSIONS", "128")

    payload = knowledge_route._vector_index_payload(
        "company-1",
        {"config": {"collectionName": "custom-collection"}},
        documents=[{"status": "indexed"}, {"status": "indexing"}],
    )

    assert payload["provider"] == "chroma"
    assert payload["collectionName"] == "custom-collection"
    assert payload["embeddingProvider"] == "hash"
    assert payload["embeddingModel"] == "hash-128"
    assert payload["indexedDocuments"] == 1
    assert payload["documentCount"] == 2


@pytest.mark.asyncio
async def test_list_documents_returns_vector_databases_and_connectors(monkeypatch, tmp_path):
    connectors = _FakeConnectorsCollection()
    documents = _FakeDocumentsCollection()
    tools = _FakeToolsCollection()
    vector_dbs = _FakeVectorDatabasesCollection()
    monkeypatch.setattr(knowledge_route, "companies_collection", _FakeCompaniesCollection())
    monkeypatch.setattr(knowledge_route, "connectors_collection", connectors)
    monkeypatch.setattr(knowledge_route, "knowledge_documents_collection", documents)
    monkeypatch.setattr(knowledge_route, "tools_collection", tools)
    monkeypatch.setattr(knowledge_route, "vector_databases_collection", vector_dbs)
    monkeypatch.setattr(knowledge_route, "KNOWLEDGE_STORAGE_DIR", tmp_path)

    result = await knowledge_route.list_knowledge_documents(email="user@example.com", companyId="company-1")

    assert len(result["vectorDatabases"]) == 2
    assert {db["name"] for db in result["vectorDatabases"]} == {"Company Knowledge", "Product Docs"}
    assert len(connectors.docs) == 2
    assert all(connector["type"] == "knowledge" for connector in connectors.docs)
