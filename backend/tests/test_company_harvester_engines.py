import pytest

from app.company_harvesters import get_company_harvester, list_company_harvesters
from app.models.company_harvester import CompanyHarvesterInput, CompanyMaterial
from app.services import infinite_company_arena


def test_company_harvester_registry_exposes_local_heuristic():
    harvesters = list_company_harvesters()
    assert {item["name"] for item in harvesters} == {"local_heuristic", "model_agent", "claude_code", "codex"}
    assert {item["kind"] for item in harvesters} == {"local_heuristic", "model_agent", "claude_code", "codex"}


@pytest.mark.asyncio
async def test_local_company_harvester_implements_output_contract():
    harvester = get_company_harvester("local")
    result = await harvester.harvest(
        CompanyHarvesterInput(
            companyId="company-1",
            companyName="Claims Co",
            materials=[
                CompanyMaterial(kind="website", name="Claims UI", url="https://claims.example.test"),
                CompanyMaterial(
                    kind="openapi",
                    name="Claims API",
                    url="https://claims.example.test/openapi.json",
                    metadata={"openapi": {"paths": {"/claims": {"get": {"operationId": "listClaims"}}}}},
                ),
                CompanyMaterial(kind="document_url", name="Claims Policy", url="https://claims.example.test/policy.md"),
            ],
        )
    )

    assert result.schemaVersion == "company_harvester_output/v1"
    assert result.companyId == "company-1"
    assert {task.expectedSurfaces[0] for task in result.proposedTasks if task.expectedSurfaces} >= {"web", "api", "documents"}
    assert result.taskSolutions
    assert all(solution.connectors and solution.tools and solution.trajectories and solution.skills for solution in result.taskSolutions)
    assert result.metadata["harvesterEngine"]["name"] == "local_heuristic"


@pytest.mark.asyncio
async def test_company_harvester_agent_engines_implement_same_contract():
    request = CompanyHarvesterInput(
        companyId="company-1",
        companyName="Claims Co",
        materials=[CompanyMaterial(kind="website", name="Claims UI", url="https://claims.example.test")],
    )

    for name in ("model_agent", "claude_code", "codex"):
        harvester = get_company_harvester(name)
        result = await harvester.harvest(request)
        assert result.schemaVersion == "company_harvester_output/v1"
        assert result.metadata["harvesterEngine"]["name"] == name
        assert result.proposedTasks
        assert result.taskSolutions


@pytest.mark.asyncio
async def test_company_harvester_engine_runner_evaluates_autoclaims_without_mongo():
    project = infinite_company_arena.load_demo_project("autoclaims")
    result = await infinite_company_arena.evaluate_project_company_harvest(
        project,
        email="owner@example.com",
        company_id="ica-engine-company",
        mode="hybrid",
        runner=infinite_company_arena.CompanyHarvesterEngineIcaRunner("local_heuristic"),
    )

    assert result.projectId == "autoclaims"
    assert result.mode == "hybrid"
    assert result.phases["inventory"]["passed"] is True
    assert result.phases["taskDiscovery"]["passed"] is True
    assert result.phases["taskDiscovery"]["recall"] == 1.0
    assert result.phases["taskDiscovery"]["matchedCount"] == 5
    assert result.phases["solutionDiscovery"]["passed"] is True
    assert result.phases["solutionDiscovery"]["solutionCount"] == 5
