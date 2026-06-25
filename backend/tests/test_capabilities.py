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
async def test_update_tool_and_skill_approval_modes(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "tools_collection",
        _Collection(
            [
                {
                    "toolId": "tool-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "crm.update",
                    "permissions": {"connectorId": "conn-1"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Update CRM",
                    "permissions": {"connectorId": "conn-1"},
                }
            ]
        ),
    )

    tool = await capabilities.update_tool_approval(
        "tool-1",
        capabilities.CapabilityApprovalUpdateRequest(email="user@example.com", approval="never"),
    )
    skill = await capabilities.update_skill_approval(
        "skill-1",
        capabilities.CapabilityApprovalUpdateRequest(email="user@example.com", approval="always"),
    )

    assert tool["tool"]["permissions"]["approval"] == "never"
    assert skill["skill"]["permissions"]["approval"] == "always"


@pytest.mark.asyncio
async def test_update_company_skill_hardening_recomputes_lineage(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection([{"runId": "run-1", "evalId": "eval-2", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"}]),
    )
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                    "connectorIds": ["conn-1"],
                    "toolIds": ["crm.search"],
                    "runtimeRequirements": ["network"],
                },
                {
                    "trajectoryId": "traj-2",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-2",
                    "evalId": "eval-2",
                    "connectorIds": ["conn-2"],
                    "toolIds": ["erp.update"],
                    "runtimeRequirements": ["browser"],
                },
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "description": "Old description",
                    "whenToUse": "Old when-to-use",
                    "riskPolicy": "human_approval_for_writes",
                    "status": "ready",
                    "trajectoryIds": ["traj-1"],
                    "connectorIds": ["conn-1"],
                    "toolIds": ["crm.search"],
                    "runtimeRequirements": ["network"],
                }
            ]
        ),
    )

    result = await capabilities.update_company_skill(
        "skill-1",
        capabilities.SkillUpdateRequest(
            email="user@example.com",
            name="Hardened renewal workflow",
            description="Reusable renewal workflow",
            whenToUse="Use for customer renewal follow-up",
            instructions="Look up the policy, confirm renewal state, draft the response and stop before sending.",
            preconditions=["Customer identity verified", "Policy number available"],
            expectedArtifacts=["draft_email", "renewal_summary"],
            riskPolicy="human_approval_always",
            status="published",
            inputEntities=["Customer", "Policy"],
            outputEntity="Draft email",
            trajectoryIds=["traj-1", "traj-2"],
        ),
    )

    skill = result["skill"]
    assert skill["name"] == "Hardened renewal workflow"
    assert skill["riskPolicy"] == "human_approval_always"
    assert skill["status"] == "published"
    assert skill["promotionStatus"] == "published"
    assert skill["version"] == 2
    assert skill["versionLabel"] == "v2"
    assert skill["publishedAt"]
    assert skill["trajectoryIds"] == ["traj-1", "traj-2"]
    assert skill["connectorIds"] == ["conn-1", "conn-2"]
    assert skill["toolIds"] == ["crm.search", "erp.update"]
    assert skill["runtimeRequirements"] == ["network", "browser"]
    assert skill["benchmarkId"] == "bench-1"
    assert skill["evalId"] == "eval-1"
    assert skill["instructions"].startswith("Look up the policy")
    assert skill["preconditions"] == ["Customer identity verified", "Policy number available"]
    assert skill["expectedArtifacts"] == ["draft_email", "renewal_summary"]
    assert skill["lineage"]["trajectoryIds"] == ["traj-1", "traj-2"]
    assert skill["lineage"]["benchmarkIds"] == ["bench-1", "bench-2"]
    assert skill["lineage"]["evalIds"] == ["eval-1", "eval-2"]
    assert skill["latestRegression"]["runId"] == "run-1"
    assert skill["latestRegression"]["label"] == "pass"
    assert skill["hardeningStatus"]["checks"]["instructions"] is True
    assert skill["hardeningStatus"]["checks"]["publishableRegression"] is True
    assert skill["hardeningStatus"]["state"] == "hardened"


@pytest.mark.asyncio
async def test_publish_skill_requires_latest_passing_benchmark(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection([{"runId": "run-1", "evalId": "eval-1", "label": "fail", "createdAt": "2026-06-25T12:00:00+00:00"}]),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_company_skill(
            "skill-1",
            capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
        )

    assert exc.value.status_code == 400
    assert "latest benchmark run is fail" in exc.value.detail


@pytest.mark.asyncio
async def test_publish_skill_requires_any_benchmark_evidence(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "eval_runs_collection", _Collection([]))

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_company_skill(
            "skill-1",
            capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
        )

    assert exc.value.status_code == 400
    assert "without benchmark evidence" in exc.value.detail


@pytest.mark.asyncio
async def test_publish_skill_allows_latest_passing_benchmark(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection(
            [
                {"runId": "run-older", "evalId": "eval-1", "label": "fail", "createdAt": "2026-06-24T12:00:00+00:00"},
                {"runId": "run-latest", "evalId": "eval-1", "label": "pass", "createdAt": "2026-06-25T12:00:00+00:00"},
            ]
        ),
    )

    result = await capabilities.update_company_skill(
        "skill-1",
        capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
    )

    assert result["skill"]["status"] == "published"
    assert result["skill"]["promotionStatus"] == "published"
    assert result["skill"]["version"] == 2
    assert result["skill"]["versionLabel"] == "v2"
    assert result["skill"]["publishedAt"]


@pytest.mark.asyncio
async def test_update_approval_rejects_invalid_mode(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "tools_collection",
        _Collection([{"toolId": "tool-1", "email": "user@example.com", "companyId": "co-1", "name": "crm.update"}]),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_tool_approval(
            "tool-1",
            capabilities.CapabilityApprovalUpdateRequest(email="user@example.com", approval="sometimes"),
        )

    assert exc.value.status_code == 400


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
    assert result["skills"][0]["promotionStatus"] == "draft"
    assert result["skills"][0]["version"] == 1
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
    assert result["skills"][0]["promotionStatus"] == "draft"
    assert result["skills"][0]["version"] == 1
    assert result["skills"][0]["runtime"] == "web_trajectory_harvester"


@pytest.mark.asyncio
async def test_promote_company_trajectory_to_skill(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "eval_runs_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
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
        capabilities.PromoteTrajectoryRequest(
            email="user@example.com",
            instructions="Fetch the latest invoice, draft the email and stop before sending.",
            preconditions=["Customer email exists"],
            expectedArtifacts=["draft_email"],
        ),
    )

    assert result["success"] is True
    assert result["skill"]["capabilityKind"] == "skill"
    assert result["skill"]["name"] == "Send latest invoice"
    assert result["skill"]["promotionStatus"] == "ready"
    assert result["skill"]["version"] == 1
    assert result["skill"]["versionLabel"] == "v1"
    assert result["skill"]["readyAt"]
    assert result["skill"]["instructions"].startswith("Fetch the latest invoice")
    assert result["skill"]["preconditions"] == ["Customer email exists"]
    assert result["skill"]["expectedArtifacts"] == ["draft_email"]
    assert result["skill"]["lineage"]["trajectoryIds"] == ["traj-1"]
    assert result["skill"]["hardeningStatus"]["checks"]["lineage"] is True
    assert result["skill"]["hardeningStatus"]["checks"]["regression"] is False

    listed = await capabilities.list_company_capabilities("co-1")
    assert listed["skills"][0]["trajectoryIds"] == ["traj-1"]
