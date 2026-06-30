import pytest

from app.routes import ica as ica_routes


@pytest.mark.asyncio
async def test_ica_routes_list_public_harvesters_and_demo_companies():
    harvesters = await ica_routes.get_harvesters()
    assert {item["name"] for item in harvesters["harvesters"]} == {"agentic", "claude_code", "codex"}

    companies = await ica_routes.get_demo_companies()
    project_ids = {item["projectId"] for item in companies["demoCompanies"]}
    assert "autoclaims" in project_ids
    autoclaims = next(item for item in companies["demoCompanies"] if item["projectId"] == "autoclaims")
    assert {"web", "openapi", "document_url"} <= set(autoclaims["surfaceKinds"])


@pytest.mark.asyncio
async def test_ica_route_runs_single_harvester_project_mode():
    response = await ica_routes.start_runs(
        ica_routes.IcaRunRequest(
            harvesterNames=["agentic"],
            projectIds=["autoclaims"],
            modeIds=["hybrid"],
        )
    )

    assert response["runGroupId"]
    assert len(response["runs"]) == 1
    run = response["runs"][0]
    assert run["harvesterName"] == "agentic"
    assert run["projectId"] == "autoclaims"
    assert run["mode"] == "hybrid"
    assert run["passed"] is True
    assert run["taskDiscoveryPassed"] is True
    assert run["taskRecall"] == 1.0
    assert run["taskMissingTaskIds"] == []
    assert run["solutionDiscoveryPassed"] is True
    assert run["solutionIncompleteTaskIds"] == []
