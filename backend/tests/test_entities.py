import pytest
from fastapi import HTTPException

from app.request_scope import RequestScope
from app.routes import entities
from app.services import agent_runtime


class _Result:
    def __init__(self, *, deleted_count=1):
        self.deleted_count = deleted_count


class _Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def sort(self, field, direction):
        reverse = direction < 0
        self.docs.sort(key=lambda item: item.get(field) or "", reverse=reverse)
        return self

    async def to_list(self, length=500):
        return [dict(doc) for doc in self.docs[:length]]

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _matches(doc, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return _Result()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)
        return _Result()

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches(doc, query)]
        return _Result(deleted_count=before - len(self.docs))


def _matches(doc, query):
    for key, value in query.items():
        if isinstance(value, dict):
            if "$in" in value and doc.get(key) not in value["$in"]:
                return False
            if "$ne" in value and doc.get(key) == value["$ne"]:
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


@pytest.mark.asyncio
async def test_create_and_graph_company_entities(monkeypatch):
    monkeypatch.setattr(entities, "companies_collection", _Collection([{"companyId": "co-1", "email": "user@example.com"}]))
    entity_collection = _Collection()
    monkeypatch.setattr(entities, "entities_collection", entity_collection)

    created = await entities.create_company_entity(
        "co-1",
        entities.EntityCreateRequest(
            email="user@example.com",
            name="Poliza",
            fields=[
                {"name": "id", "type": "string", "role": "identifier"},
                {"name": "clienteId", "type": "string", "ref": "Cliente"},
            ],
            relationships=[{"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"}],
        ),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert created["success"] is True
    assert created["entity"]["name"] == "Poliza"
    assert created["entity"]["entityMapping"]["businessObject"] == "Poliza"
    assert created["entity"]["entityMapping"]["relationshipTargets"] == ["Cliente"]
    assert "aliases" in created["entity"]["entityMapping"]["readiness"]["gaps"]

    await entities.create_company_entity(
        "co-1",
        entities.EntityCreateRequest(
            email="user@example.com",
            name="Cliente",
            sourceConnectorId="conn-1",
            metadata={"aliases": ["Customer"], "permissions": {"scopes": ["crm:read"]}},
        ),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )
    graph = await entities.company_entity_graph(
        "co-1",
        email="user@example.com",
        scope=RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert {node["name"] for node in graph["nodes"]} == {"Cliente", "Poliza"}
    assert graph["edges"] == [{"from": "Poliza", "to": "Cliente", "name": "cliente", "kind": "belongsTo", "via": "clienteId", "description": ""}]
    cliente = next(item for item in graph["entities"] if item["name"] == "Cliente")
    assert cliente["entityMapping"]["aliases"] == ["Customer"]
    assert cliente["entityMapping"]["permissions"]["scopes"] == ["crm:read"]


@pytest.mark.asyncio
async def test_entity_name_is_unique_per_company(monkeypatch):
    monkeypatch.setattr(entities, "companies_collection", _Collection([{"companyId": "co-1", "email": "user@example.com"}]))
    monkeypatch.setattr(entities, "entities_collection", _Collection([{"entityId": "ent-1", "companyId": "co-1", "email": "user@example.com", "name": "Cliente"}]))

    with pytest.raises(HTTPException) as exc:
        await entities.create_company_entity(
            "co-1",
            entities.EntityCreateRequest(email="user@example.com", name="Cliente"),
            RequestScope(email="user@example.com", token_email="user@example.com"),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_generate_entities_from_openapi_applies_to_company(monkeypatch):
    monkeypatch.setattr(entities, "companies_collection", _Collection([{"companyId": "co-1", "email": "user@example.com"}]))
    entity_collection = _Collection()
    monkeypatch.setattr(entities, "entities_collection", entity_collection)

    async def fake_propose(source_url):
        return [
            {
                "name": "Cliente",
                "description": "Customer record",
                "fields": [{"name": "id", "type": "string", "role": "identifier"}],
                "relationships": [],
                "metadata": {"schemaName": "CustomerRead", "sourceUrl": source_url},
            },
            {
                "name": "Poliza",
                "description": "Policy record",
                "fields": [{"name": "clienteId", "type": "string", "role": "reference"}],
                "relationships": [{"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"}],
                "metadata": {"schemaName": "PolicyRead", "sourceUrl": source_url},
            },
        ]

    monkeypatch.setattr(entities, "propose_entities_from_openapi_url", fake_propose)

    result = await entities.generate_company_entities(
        "co-1",
        entities.EntityGenerateRequest(
            email="user@example.com",
            sourceUrl="https://example.com/openapi.json",
            apply=True,
        ),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert result["success"] is True
    assert result["applied"] is True
    assert [item["name"] for item in result["entities"]] == ["Cliente", "Poliza"]
    assert len(entity_collection.docs) == 2
    assert entity_collection.docs[1]["source"] == "openapi"
    assert entity_collection.docs[1]["relationships"][0]["target"] == "Cliente"


@pytest.mark.asyncio
async def test_generate_entities_can_resolve_source_from_connector(monkeypatch):
    monkeypatch.setattr(entities, "companies_collection", _Collection([{"companyId": "co-1", "email": "user@example.com"}]))
    monkeypatch.setattr(
        entities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "config": {"openApiUrl": "https://erp.example.com/openapi.json"},
                }
            ]
        ),
    )
    entity_collection = _Collection()
    monkeypatch.setattr(entities, "entities_collection", entity_collection)

    async def fake_propose(source_url):
        return [{"name": "Siniestro", "metadata": {"sourceUrl": source_url}}]

    monkeypatch.setattr(entities, "propose_entities_from_openapi_url", fake_propose)

    result = await entities.generate_company_entities(
        "co-1",
        entities.EntityGenerateRequest(email="user@example.com", sourceConnectorId="conn-1", apply=True),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert result["sourceUrl"] == "https://erp.example.com/openapi.json"
    assert result["sourceConnectorId"] == "conn-1"
    assert entity_collection.docs[0]["sourceConnectorId"] == "conn-1"
    assert entity_collection.docs[0]["metadata"]["sourceConnectorId"] == "conn-1"


@pytest.mark.asyncio
async def test_runtime_capability_context_includes_relevant_entity_graph(monkeypatch):
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _Collection())
    monkeypatch.setattr(
        agent_runtime,
        "tools_collection",
        _Collection(
            [
                {
                    "toolId": "tool-1",
                    "companyId": "co-1",
                    "name": "erp.search_policies",
                    "description": "Search policies",
                    "outputEntity": "Poliza",
                    "inputEntities": [],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        agent_runtime,
        "entities_collection",
        _Collection(
            [
                {
                    "entityId": "ent-poliza",
                    "companyId": "co-1",
                    "name": "Poliza",
                    "fields": [{"name": "clienteId", "type": "string", "ref": "Cliente"}],
                    "relationships": [{"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"}],
                },
                {"entityId": "ent-cliente", "companyId": "co-1", "name": "Cliente", "fields": [{"name": "id", "type": "string"}]},
                {"entityId": "ent-recibo", "companyId": "co-1", "name": "Recibo"},
            ]
        ),
    )

    context = await agent_runtime._capability_context({"agentId": "agent-1", "companyId": "co-1"})

    assert context["callables"][0]["outputEntity"] == "Poliza"
    assert {node["name"] for node in context["entities"]["nodes"]} == {"Cliente", "Poliza"}
    assert context["entities"]["edges"][0]["from"] == "Poliza"
