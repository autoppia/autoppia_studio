from app.services.manual_skill_assets import attach_manual_skill_assets
from app.services.manual_skill_assets import dedupe_manual_skill_values
from app.services.manual_skill_assets import flatten_manual_skill_values
from app.services.manual_skill_assets import manual_skill_hardening
from app.services.manual_skill_assets import manual_skill_lineage
from app.services.manual_skill_assets import manual_skill_package
from app.services.skill_packages import skill_package_readiness
from app.services.skill_packages import summarize_skill_packages


def _manual_skill_doc():
    return {
        "capabilityId": "skill-1",
        "name": "Handle claim status",
        "description": "Search claim state and draft the customer reply.",
        "whenToUse": "Use for customer claim status requests.",
        "instructions": "Search the claim and draft a reply without sending.",
        "trajectoryIds": ["traj-1", "traj-1"],
        "benchmarkIds": ["bench-1", "bench-1"],
        "evalId": "task-1",
        "evalIds": ["task-1", "task-2"],
        "connectorIds": ["imap", "erp"],
        "toolIds": ["imap.read_email", "erp.claims.get"],
        "expectedArtifacts": ["draft_email"],
        "preconditions": ["Customer identity verified"],
        "inputEntities": ["Claim"],
        "outputEntity": "Draft email",
        "riskPolicy": "human_approval_for_writes",
        "permissions": {"approval": "always"},
        "runtime": "trajectory_replay_with_recovery",
        "runtimeRequirements": ["browser"],
        "promotionStatus": "ready",
        "version": 1,
        "versionLabel": "v1",
        "versionHistory": [{"version": 1, "reason": "manual_skill_created"}],
        "source": "manual_agent_asset",
        "createdAt": "2026-06-26T10:00:00+00:00",
        "updatedAt": "2026-06-26T10:00:00+00:00",
    }


def test_dedupe_manual_skill_values_preserves_order():
    assert dedupe_manual_skill_values([" Claim ", "Claim", "", None, "Policy"]) == ["Claim", "Policy"]


def test_flatten_manual_skill_values_accepts_singletons_and_lists():
    assert flatten_manual_skill_values("bench-1", ["bench-1", "bench-2"], None) == ["bench-1", "bench-2"]


def test_manual_skill_lineage_and_hardening_capture_reusable_skill_evidence():
    doc = _manual_skill_doc()
    lineage = manual_skill_lineage(doc)
    hardening = manual_skill_hardening(doc, lineage)

    assert lineage == {
        "trajectoryIds": ["traj-1"],
        "benchmarkIds": ["bench-1"],
        "evalIds": ["task-1", "task-2"],
        "connectorIds": ["imap", "erp"],
        "toolIds": ["imap.read_email", "erp.claims.get"],
        "sources": ["manual_agent_asset"],
    }
    assert hardening["checks"]["activation"] is True
    assert hardening["checks"]["lineage"] is True
    assert hardening["checks"]["regression"] is True
    assert hardening["checks"]["publishableRegression"] is False
    assert hardening["state"] == "drafting"


def test_manual_skill_package_keeps_existing_agent_skill_contract():
    doc = _manual_skill_doc()
    lineage = manual_skill_lineage(doc)
    hardening = manual_skill_hardening(doc, lineage)
    package = manual_skill_package(doc, lineage, hardening)
    readiness = skill_package_readiness({"skillPackage": package, **doc})

    assert package["format"] == "autoppia.agent_skill"
    assert package["metadata"]["promotionStatus"] == "ready"
    assert package["ioContract"]["inputs"]["entities"] == ["Claim"]
    assert package["ioContract"]["outputs"]["artifacts"] == ["draft_email"]
    assert package["execution"]["trajectoryIds"] == ["traj-1"]
    assert package["policies"]["runtimePolicy"]["approvalMode"] == "always"
    assert package["hardening"]["readyForPublish"] is False
    assert package["hardening"]["blockers"] == ["publishableRegression"]
    assert package["productionGate"]["state"] == "needs_regression"
    assert package["productionGate"]["checks"]["sourceTrajectory"] is True
    assert package["evidence"]["regressionSuite"] == {
        "benchmarkIds": ["bench-1"],
        "evalIds": ["task-1", "task-2"],
        "cases": [],
        "publishable": False,
    }
    assert readiness["checks"]["regressionSuite"] is True
    assert readiness["release"]["promotionStatus"] == "ready"
    assert readiness["release"]["version"] == 1
    assert readiness["release"]["historyCount"] == 1
    assert readiness["hardening"]["blockers"] == ["publishableRegression"]


def test_attach_manual_skill_assets_returns_skill_with_lineage_hardening_and_package():
    skill = attach_manual_skill_assets(_manual_skill_doc())

    assert skill["lineage"]["trajectoryIds"] == ["traj-1"]
    assert skill["hardeningStatus"]["checks"]["artifacts"] is True
    assert skill["skillPackage"]["packageId"] == "skill-1"


def test_summarize_skill_packages_exposes_release_readiness_and_status_counts():
    ready = attach_manual_skill_assets(_manual_skill_doc())
    published = {
        **ready,
        "capabilityId": "skill-2",
        "name": "Published claim handler",
        "promotionStatus": "published",
        "latestRegression": {"label": "pass"},
        "version": 2,
        "versionHistory": [
            {"version": 1, "promotionStatus": "ready", "reason": "initial", "createdAt": "t-1"},
            {"version": 2, "promotionStatus": "published", "reason": "promotion", "createdAt": "t-2"},
        ],
    }
    published = attach_manual_skill_assets(published)

    summary = summarize_skill_packages([ready, published], package_limit=2)

    assert summary["releaseStatus"] == [{"name": "published", "count": 1}, {"name": "ready", "count": 1}]
    assert summary["releaseReadiness"] == {
        "readyForPublish": 1,
        "published": 1,
        "withVersionHistory": 1,
        "draft": 0,
        "ready": 1,
        "archived": 0,
    }
    assert summary["sample"][1]["promotionStatus"] == "published"
    assert summary["packages"][1]["release"]["latestEvent"]["reason"] == "promotion"
