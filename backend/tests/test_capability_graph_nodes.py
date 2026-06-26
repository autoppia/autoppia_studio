from app.services.capability_graph_nodes import add_edge
from app.services.capability_graph_nodes import add_node
from app.services.capability_graph_nodes import approval_mode_payload
from app.services.capability_graph_nodes import browser_policy_id
from app.services.capability_graph_nodes import browser_policy_payload
from app.services.capability_graph_nodes import capability_boundary
from app.services.capability_graph_nodes import entity_names
from app.services.capability_graph_nodes import eval_run_payload
from app.services.capability_graph_nodes import runtime_ref
from app.services.capability_graph_nodes import runtime_ref_list
from app.services.capability_graph_nodes import session_runtime_payload
from app.services.capability_graph_nodes import tool_lookup
from app.services.capability_graph_nodes import work_item_payload
from app.services.capability_graph_nodes import work_ref_list


def test_graph_node_and_edge_helpers_dedupe_by_stable_ids():
    nodes = {}
    edges = {}

    first = add_node(nodes, "skill", "skill-1", "Handle claim", {"version": 1})
    second = add_node(nodes, "skill", "skill-1", "Ignored duplicate", {"version": 2})
    add_edge(edges, "task:task-1", first, "promoted_to", {"source": "test"})
    add_edge(edges, "task:task-1", first, "promoted_to", {"source": "duplicate"})
    add_edge(edges, "", first, "ignored")

    assert first == "skill:skill-1"
    assert second == "skill:skill-1"
    assert nodes[first]["label"] == "Handle claim"
    assert list(edges) == ["task:task-1->promoted_to->skill:skill-1"]
    assert edges["task:task-1->promoted_to->skill:skill-1"]["evidence"] == {"source": "test"}


def test_entity_and_tool_lookups_include_aliases_and_names():
    entities = entity_names(
        [
            {
                "entityId": "entity-1",
                "name": "Claim",
                "metadata": {"aliases": ["Siniestro"], "businessAliases": ["Ignored by precedence"]},
            }
        ]
    )
    tools = tool_lookup([{"toolId": "tool-1", "name": "erp.claims.get"}])

    assert entities["claim"]["entityId"] == "entity-1"
    assert entities["siniestro"]["entityId"] == "entity-1"
    assert tools["tool-1"]["name"] == "erp.claims.get"
    assert tools["erp.claims.get"]["toolId"] == "tool-1"


def test_runtime_refs_resolve_nested_runtime_shapes_and_tool_lists():
    session = {
        "runtimeState": {
            "capabilityMatch": {"matchedSkillId": "skill-from-camel"},
            "runtimeEvidence": {"toolIds": ["tool-runtime"]},
        },
        "runtimeEvidence": {"capabilityRefs": {"skillId": "skill-from-evidence"}},
        "operational": {"toolIds": ["tool-operational"]},
        "latestToolIds": ["tool-latest"],
        "metadata": {"toolIds": ["tool-metadata"]},
    }

    assert runtime_ref(session, "matchedSkillId") == "skill-from-camel"
    assert runtime_ref_list(session, "toolIds") == ["tool-metadata", "tool-operational", "tool-runtime", "tool-latest"]


def test_runtime_payloads_capture_session_work_policy_and_eval_state():
    session_payload = session_runtime_payload(
        {
            "sessionId": "session-1",
            "prompt": "Draft a claim response",
            "runtimeState": {
                "runtimeKind": "hybrid",
                "matchedSkillId": "skill-1",
                "pendingApprovalCount": 1,
                "traceIds": ["trace-1"],
            },
        }
    )
    work_payload = work_item_payload(
        {
            "workItemId": "work-1",
            "status": "REVIEW",
            "operational": {
                "reviewBlocked": True,
                "latestSessionIds": ["session-1"],
                "orchestration": {"budget": {"max": 5}},
            },
        }
    )
    eval_payload = eval_run_payload({"runId": "run-1", "label": "PASS", "evalId": "task-1"})

    assert session_payload["runtimeKind"] == "hybrid"
    assert session_payload["matchedSkillId"] == "skill-1"
    assert session_payload["pendingApprovalCount"] == 1
    assert work_payload["reviewBlocked"] is True
    assert work_payload["orchestration"] == {"budget": {"max": 5}}
    assert work_ref_list({"operational": {"latestSessionIds": ["session-1", "session-1"]}}, "latestSessionIds") == ["session-1"]
    assert eval_payload["label"] == "pass"


def test_policy_payloads_model_boundaries_approvals_and_browser_sandboxing():
    browser_policy = {
        "browserRuntime": True,
        "browserPolicy": {
            "defaultUse": "exception",
            "restrictedByDomain": True,
            "allowedDomains": ["erp.example.com"],
            "requiresSandbox": True,
        },
    }

    assert capability_boundary({"sideEffects": "sends"}) == "send"
    assert approval_mode_payload("invalid")["approvalMode"] == "auto"
    assert browser_policy_id(browser_policy) == "domain_restricted"
    assert browser_policy_payload(browser_policy) == {
        "browserPolicy": "domain_restricted",
        "browserRuntime": True,
        "defaultUse": "exception",
        "restrictedByDomain": True,
        "allowedDomains": ["erp.example.com"],
        "requiresSandbox": True,
        "leastPrivilege": True,
    }
