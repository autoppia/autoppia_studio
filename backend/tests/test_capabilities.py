import pytest
from fastapi import HTTPException

from app.routes import capabilities


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

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
        return _Result(matched_count=0)


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, option) for option in value):
                return False
            continue
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


@pytest.mark.asyncio
async def test_publish_official_connector_publishes_default_tools(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Cloudflare",
                    "type": "cloudflare",
                    "status": "connected",
                    "provider": "official",
                    "config": {},
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.publish_connector_tools("conn-1")

    assert result["success"] is True
    assert result["run"]["status"] == "completed"
    assert result["run"]["runKind"] == "tool_publication"
    assert result["run"]["harvesterType"] == "default_toolkit_publisher"
    assert {tool["name"] for tool in result["tools"]} >= {"cloudflare.search", "cloudflare.get"}
    assert {tool["source"] for tool in result["tools"]} == {"default_toolkit"}

    listed = await capabilities.list_company_capabilities("co-1")
    assert [item["capabilityKind"] for item in listed["capabilities"]] == ["tool", "tool", "tool", "tool"]


@pytest.mark.asyncio
async def test_official_connector_rejects_harvester(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Cloudflare",
                    "type": "cloudflare",
                    "status": "connected",
                    "provider": "official",
                    "config": {},
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.harvest_connector("conn-1")

    assert exc.value.status_code == 400
    assert "default tools" in exc.value.detail


@pytest.mark.asyncio
async def test_custom_api_connector_uses_harvester(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"openApiUrl": "https://example.com/openapi.json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_connector("conn-1")

    assert result["success"] is True
    assert result["run"]["runKind"] == "harvester"
    assert result["run"]["harvesterType"] == "api_harvester"
    assert all(tool["source"] == "harvested_toolkit" for tool in result["tools"])


@pytest.mark.asyncio
async def test_custom_api_benchmark_harvest_generates_tools_and_skills(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"openApiUrl": "https://example.com/openapi.json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "evals_collection",
        _Collection(
            [
                {
                    "evalId": "ev-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "prompt": "Create a new CRM lead",
                    "successCriteria": "Lead exists",
                    "createdAt": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_connector_benchmark(
        "conn-1",
        capabilities.ConnectorBenchmarkHarvestRequest(benchmarkId="bench-1"),
    )

    assert result["success"] is True
    assert result["run"]["runKind"] == "benchmark_harvester"
    assert result["run"]["discoveredTools"] > 0
    assert result["run"]["generatedSkills"] == 1
    assert result["skills"][0]["status"] == "draft"
    assert result["skills"][0]["trajectoryIds"] == ["conn-1:ev-1:trajectory"]


@pytest.mark.asyncio
async def test_company_capabilities_harvest_is_canonical_endpoint(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"openApiUrl": "https://example.com/openapi.json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "evals_collection",
        _Collection(
            [
                {
                    "evalId": "ev-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "prompt": "Create a new CRM lead",
                    "successCriteria": "Lead exists",
                    "createdAt": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_company_capabilities(
        "co-1",
        capabilities.CompanyCapabilityHarvestRequest(connectorId="conn-1", benchmarkId="bench-1"),
    )

    assert result["success"] is True
    assert result["run"]["runKind"] == "benchmark_harvester"
    assert result["run"]["generatedSkills"] == 1


@pytest.mark.asyncio
async def test_company_capabilities_harvest_rejects_connector_from_other_company(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-2",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {},
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.harvest_company_capabilities(
            "co-1",
            capabilities.CompanyCapabilityHarvestRequest(connectorId="conn-1", benchmarkId="bench-1"),
        )

    assert exc.value.status_code == 400
    assert "does not belong" in exc.value.detail


@pytest.mark.asyncio
async def test_custom_web_benchmark_harvest_generates_skills_without_tools(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "BOPA Portal",
                    "type": "web",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"startUrl": "https://www.bopa.ad/"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "evals_collection",
        _Collection(
            [
                {
                    "evalId": "ev-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "prompt": "Find the latest BOPA notice",
                    "successCriteria": "Notice is summarized",
                    "createdAt": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_connector_benchmark(
        "conn-1",
        capabilities.ConnectorBenchmarkHarvestRequest(benchmarkId="bench-1"),
    )

    assert result["success"] is True
    assert result["tools"] == []
    assert result["run"]["generatedSkills"] == 1
    assert result["skills"][0]["status"] == "needs_harvest"
    assert result["skills"][0]["runtime"] == "web_trajectory_harvester"


@pytest.mark.asyncio
async def test_promote_company_trajectory_to_skill(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(
        capabilities,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Send latest invoice",
                    "intent": "Send the latest invoice to a client",
                    "connectorIds": ["gmail", "holded"],
                    "toolIds": ["holded.get_invoice", "gmail.send_email"],
                    "steps": [],
                    "status": "approved",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.promote_trajectory_to_skill(
        "traj-1",
        capabilities.PromoteTrajectoryRequest(email="user@example.com"),
    )

    assert result["success"] is True
    assert result["skill"]["capabilityKind"] == "skill"
    assert result["skill"]["name"] == "Send latest invoice"

    listed = await capabilities.list_company_capabilities("co-1")
    assert listed["skills"][0]["trajectoryIds"] == ["traj-1"]
