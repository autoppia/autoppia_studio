import json

import pytest

from app.company_harvesters import get_company_harvester, list_company_harvesters
from app.company_harvesters.agent_engines import CliCompanyHarvester, validate_company_harvester_output
from app.models.company_harvester import CompanyHarvesterInput, CompanyMaterial
from app.services import infinite_company_arena


class _FakeCliCompanyHarvester(CliCompanyHarvester):
    def __init__(self, outputs):
        object.__setattr__(self, "name", "claude_code")
        object.__setattr__(self, "kind", "claude_code")
        object.__setattr__(self, "display_name", "Claude Code Harvester")
        object.__setattr__(self, "command", "claude")
        object.__setattr__(self, "runtime_kind", "claude_code")
        object.__setattr__(self, "outputs", list(outputs))
        object.__setattr__(self, "prompts", [])

    async def _run_prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("No fake output queued")
        return self.outputs.pop(0)


def test_company_harvester_registry_exposes_public_miners():
    harvesters = list_company_harvesters()
    assert {item["name"] for item in harvesters} == {"agentic", "claude_code", "codex"}
    assert {item["kind"] for item in harvesters} == {"agentic", "claude_code", "codex"}
    assert all(item["displayName"] for item in harvesters)


def test_company_harvester_output_checker_normalizes_string_questions():
    request = CompanyHarvesterInput(companyId="company-1")
    check = validate_company_harvester_output(
        {
            "companyId": "company-1",
            "proposedTasks": [{"taskId": "task-1", "name": "Task 1", "prompt": "Do task 1"}],
            "taskSolutions": [{"taskId": "task-1"}],
            "questions": ["Which auth role should be used?"],
        },
        request,
        engine_name="claude_code",
        engine_kind="claude_code",
        runtime_kind="claude_code",
    )

    assert check["valid"] is True
    output = check["output"]
    assert output.questions[0]["prompt"] == "Which auth role should be used?"
    assert output.questions[0]["metadata"]["normalizedFrom"] == "string"
    assert check["warnings"] == ["normalized questions entries into objects"]


@pytest.mark.asyncio
async def test_cli_company_harvester_repairs_invalid_output_contract(monkeypatch):
    monkeypatch.setenv("AUTOMATA_CLI_HARVESTER_REPAIR_ATTEMPTS", "1")
    request = CompanyHarvesterInput(
        companyId="company-1",
        companyName="Demo Co",
        materials=[CompanyMaterial(kind="website", name="Demo UI", url="https://demo.example.test")],
    )
    invalid = {
        "companyId": "company-1",
        "proposedTasks": [{"taskId": "task-1", "name": "Task 1", "prompt": "Do task 1"}],
        "taskSolutions": [
            {
                "taskId": "task-1",
                "tools": [
                    {
                        "name": "demo.custom",
                        "origin": "proposed_custom",
                        "customToolCode": {"language": "pseudo", "functionName": "run", "code": "click around"},
                    }
                ],
            }
        ],
    }
    repaired = {
        "companyId": "company-1",
        "proposedTasks": [{"taskId": "task-1", "name": "Task 1", "prompt": "Do task 1"}],
        "taskSolutions": [
            {
                "taskId": "task-1",
                "tools": [{"name": "demo.web.explore_workflows", "origin": "existing_connector_tool"}],
                "skills": [{"name": "Task 1 skill", "instructions": "Use the browser workflow guidance instead of pseudocode."}],
                "agentProvider": {"runtimeKind": "claude_code", "provider": "anthropic"},
            }
        ],
    }
    harvester = _FakeCliCompanyHarvester([f"```json\n{json.dumps(invalid)}\n```", f"```json\n{json.dumps(repaired)}\n```"])

    result = await harvester.harvest(request)

    assert result.metadata["harvesterEngine"]["repairAttempts"] == 1
    assert result.taskSolutions[0].tools[0].customToolCode is None
    assert result.taskSolutions[0].agentProvider.runtimeKind == "claude_code"
    assert len(harvester.prompts) == 2
    assert "failed schema validation" in harvester.prompts[1]
    assert "pseudo/pseudocode is not executable code" in harvester.prompts[1]


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
    assert result.metadata["harvesterEngine"]["name"] == "agentic"


@pytest.mark.asyncio
async def test_company_harvester_agent_engines_implement_same_contract():
    request = CompanyHarvesterInput(
        companyId="company-1",
        companyName="Claims Co",
        materials=[CompanyMaterial(kind="website", name="Claims UI", url="https://claims.example.test")],
    )

    harvester = get_company_harvester("agentic")
    result = await harvester.harvest(request)
    assert result.schemaVersion == "company_harvester_output/v1"
    assert result.metadata["harvesterEngine"]["name"] == "agentic"
    assert result.proposedTasks
    assert result.taskSolutions

    for name in ("claude_code", "codex"):
        info = get_company_harvester(name).info()
        assert info.name == name
        assert info.status in {"ready", "missing_cli"}
        assert info.metadata["execution"] == "real_cli"


@pytest.mark.asyncio
async def test_company_harvester_engine_runner_evaluates_autoclaims_without_mongo():
    project = infinite_company_arena.load_demo_project("autoclaims")
    result = await infinite_company_arena.evaluate_project_company_harvest(
        project,
        email="owner@example.com",
        company_id="ica-engine-company",
        mode="all_sources",
        runner=infinite_company_arena.CompanyHarvesterEngineIcaRunner("local_heuristic"),
    )

    assert result.projectId == "autoclaims"
    assert result.mode == "all_sources"
    assert result.phases["inventory"]["passed"] is True
    assert result.phases["taskDiscovery"]["passed"] is True
    assert result.phases["taskDiscovery"]["recall"] == 1.0
    assert result.phases["taskDiscovery"]["matchedCount"] == 5
    assert result.phases["solutionDiscovery"]["passed"] is True
    assert result.phases["solutionDiscovery"]["solutionCount"] == 5
