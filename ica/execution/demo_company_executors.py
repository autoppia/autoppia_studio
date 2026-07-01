from __future__ import annotations

from typing import Any, Protocol

from app.models.agent_config import AgentConfig
from ica.iwa_bridge import iwa_tests, load_iwa_trajectory_map
from ica.schemas import IcaAgentExecutionTaskResult, IcaTaskSolutionSpec


class DemoCompanyExecutor(Protocol):
    project_id: str

    def run_task(
        self,
        *,
        task: Any,
        solution: IcaTaskSolutionSpec,
        agent: AgentConfig,
    ) -> IcaAgentExecutionTaskResult:
        """Execute one benchmark task against a demo-company test harness."""


def executed_tool_names(solution: IcaTaskSolutionSpec) -> list[str]:
    names: list[str] = []
    for trajectory in solution.trajectories:
        for call in trajectory.toolCalls:
            if isinstance(call, dict):
                name = str(call.get("toolName") or call.get("name") or call.get("tool") or "")
                if name:
                    names.append(name)
    return list(dict.fromkeys(names))


def has_tool(executed_tools: list[str], expected: str) -> bool:
    expected_clean = expected.lower()
    return any(tool.lower() == expected_clean or tool.lower().endswith(expected_clean) for tool in executed_tools)


def matching_tool_calls(solution: IcaTaskSolutionSpec, expected: str) -> list[dict[str, Any]]:
    expected_clean = expected.lower()
    calls: list[dict[str, Any]] = []
    for trajectory in solution.trajectories:
        for call in trajectory.toolCalls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("toolName") or call.get("name") or call.get("tool") or "")
            if name.lower() == expected_clean or name.lower().endswith(expected_clean):
                calls.append(call)
    return calls


def call_arguments(call: dict[str, Any]) -> dict[str, Any]:
    args = call.get("arguments")
    return args if isinstance(args, dict) else {}


def has_call_arg(solution: IcaTaskSolutionSpec, tool_name: str, key_options: list[str], expected: str) -> bool:
    expected_clean = str(expected).lower()
    for call in matching_tool_calls(solution, tool_name):
        args = call_arguments(call)
        for key in key_options:
            value = args.get(key)
            if str(value or "").lower() == expected_clean:
                return True
    return False


def has_call_arg_containing(solution: IcaTaskSolutionSpec, tool_name: str, key_options: list[str], expected: str) -> bool:
    expected_clean = str(expected).lower()
    for call in matching_tool_calls(solution, tool_name):
        args = call_arguments(call)
        for key in key_options:
            value = args.get(key)
            if expected_clean in str(value or "").lower():
                return True
    return False


def assertion(label: str, passed: bool, expected: Any = None, actual: Any = None) -> dict[str, Any]:
    return {"label": label, "passed": passed, "expected": expected, "actual": actual}


def _tokens(value: str) -> set[str]:
    stop = {"the", "and", "for", "with", "using", "use", "from", "into", "web", "ui", "iwa", "event", "test", "is", "to"}
    clean = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or ""))
    return {part for part in clean.split() if len(part) > 2 and part not in stop}


def semantic_goal_match(expected_text: str, actual_values: list[Any], *, min_overlap: float = 0.35) -> bool:
    expected = _tokens(expected_text)
    actual = _tokens(" ".join(str(value or "") for value in actual_values))
    if not expected or not actual:
        return False
    return (len(expected & actual) / len(expected)) >= min_overlap


class AutoCommerceExecutor:
    project_id = "autocommerce"

    def run_task(
        self,
        *,
        task: Any,
        solution: IcaTaskSolutionSpec,
        agent: AgentConfig,
    ) -> IcaAgentExecutionTaskResult:
        test = task.metadata.get("executionTest") if isinstance(task.metadata.get("executionTest"), dict) else {}
        test_type = str(test.get("type") or "")
        executed_tools = executed_tool_names(solution)
        assertions: list[dict[str, Any]] = []
        state: dict[str, Any] = {"orders": {}, "refundDrafts": [], "inventoryNotes": {}}

        for required in test.get("requiredTools") or []:
            assertions.append(assertion(f"required tool {required}", has_tool(executed_tools, str(required)), True, executed_tools))
        any_tools = [str(item) for item in test.get("requiredAnyTools") or []]
        if any_tools:
            assertions.append(assertion("one required tool available", any(has_tool(executed_tools, item) for item in any_tools), any_tools, executed_tools))

        if test_type == "autocommerce_order_status":
            order = {
                "orderId": str(test.get("orderId") or "ORD-1001"),
                "status": "in_transit",
                "carrier": "DHL",
                "latestCustomerNote": "Customer asked for delivery ETA this morning.",
            }
            has_order_arg = has_call_arg(solution, "autocommerce.api.getorder", ["orderId", "order_id", "id"], order["orderId"])
            assertions.append(assertion("get order argument", has_order_arg, order["orderId"], [call_arguments(call) for call in matching_tool_calls(solution, "autocommerce.api.getorder")]))
            if has_order_arg:
                state["orders"][order["orderId"]] = order
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            actual = state["orders"].get(order["orderId"], {})
            assertions.extend(
                [
                    assertion("order status", actual.get("status") == expected.get("status"), expected.get("status"), actual.get("status")),
                    assertion("carrier", actual.get("carrier") == expected.get("carrier"), expected.get("carrier"), actual.get("carrier")),
                    assertion(
                        "latest note",
                        str(expected.get("latestCustomerNoteContains") or "").lower() in str(actual.get("latestCustomerNote") or "").lower(),
                        expected.get("latestCustomerNoteContains"),
                        actual.get("latestCustomerNote"),
                    ),
                ]
            )
        elif test_type == "autocommerce_refund_draft":
            order_id = str(test.get("orderId") or "ORD-2002")
            has_order_arg = has_call_arg(solution, "autocommerce.api.getorder", ["orderId", "order_id", "id"], order_id)
            has_refund_arg = has_call_arg(solution, "autocommerce.api.draftrefund", ["orderId", "order_id", "id"], order_id)
            has_policy_query = has_call_arg_containing(solution, "knowledge.company_docs.search", ["query", "q"], "refund")
            assertions.extend(
                [
                    assertion("get delayed order argument", has_order_arg, order_id, [call_arguments(call) for call in matching_tool_calls(solution, "autocommerce.api.getorder")]),
                    assertion("refund draft order argument", has_refund_arg, order_id, [call_arguments(call) for call in matching_tool_calls(solution, "autocommerce.api.draftrefund")]),
                    assertion("refund policy query", has_policy_query, "refund", [call_arguments(call) for call in matching_tool_calls(solution, "knowledge.company_docs.search")]),
                ]
            )
            if has_order_arg:
                state["orders"][order_id] = {"orderId": order_id, "status": "delayed", "carrier": "UPS", "delayHours": 96}
            policy_checked = has_policy_query
            if policy_checked and has_refund_arg:
                state["refundDrafts"].append(
                    {"orderId": order_id, "reason": "Delayed shipment exceeds 72 hours", "policyReference": "Fulfillment Policy 72 hours"}
                )
            draft = next((item for item in state["refundDrafts"] if item.get("orderId") == order_id), {})
            assertions.extend(
                [
                    assertion("policy checked", policy_checked, True, policy_checked),
                    assertion("refund draft created", bool(draft), True, draft),
                    assertion("policy reference", "72" in str(draft.get("policyReference") or ""), "contains 72", draft.get("policyReference")),
                ]
            )
        elif test_type == "autocommerce_inventory_note":
            sku = str(test.get("sku") or "SKU-RED-MUG")
            has_api_sku = has_call_arg(solution, "autocommerce.api.addinventorynote", ["sku", "productSku", "product_sku"], sku)
            has_web_sku = has_call_arg_containing(solution, "autocommerce.web.explore_workflows", ["goal", "intent", "task", "description"], sku)
            assertions.append(
                assertion(
                    "inventory note target sku",
                    has_api_sku or has_web_sku,
                    sku,
                    {
                        "api": [call_arguments(call) for call in matching_tool_calls(solution, "autocommerce.api.addinventorynote")],
                        "web": [call_arguments(call) for call in matching_tool_calls(solution, "autocommerce.web.explore_workflows")],
                    },
                )
            )
            if has_api_sku or has_web_sku:
                state["inventoryNotes"][sku] = ["SKU-RED-MUG needs supplier confirmation before restock."]
            note_text = " ".join(state["inventoryNotes"].get(sku, []))
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            assertions.append(
                assertion(
                    "inventory note",
                    str(expected.get("noteContains") or "").lower() in note_text.lower(),
                    expected.get("noteContains"),
                    note_text,
                )
            )
        else:
            assertions.append(assertion("known execution test", False, "known test type", test_type))

        passed = bool(assertions) and all(item.get("passed") for item in assertions)
        score = round(sum(1 for item in assertions if item.get("passed")) / len(assertions), 4) if assertions else 0.0
        return IcaAgentExecutionTaskResult(
            taskId=task.taskId,
            passed=passed,
            score=score,
            agentId=agent.agentId,
            executedTools=executed_tools,
            assertions=assertions,
            state=state,
        )


class AutoClaimsExecutor:
    project_id = "autoclaims"

    def run_task(
        self,
        *,
        task: Any,
        solution: IcaTaskSolutionSpec,
        agent: AgentConfig,
    ) -> IcaAgentExecutionTaskResult:
        test = task.metadata.get("executionTest") if isinstance(task.metadata.get("executionTest"), dict) else {}
        test_type = str(test.get("type") or "")
        executed_tools = executed_tool_names(solution)
        assertions: list[dict[str, Any]] = []
        state: dict[str, Any] = {
            "claims": {
                "CLM-1001": {
                    "claimId": "CLM-1001",
                    "status": "open",
                    "customerName": "Ada Lovelace",
                    "latestNote": "Photos received and damage amount below approval limit.",
                    "risk": "low",
                    "decision": "",
                },
                "CLM-2002": {
                    "claimId": "CLM-2002",
                    "status": "flagged",
                    "customerName": "Grace Hopper",
                    "latestNote": "Fraud signal and high value claim require review.",
                    "risk": "high",
                    "decision": "",
                },
                "CLM-3003": {
                    "claimId": "CLM-3003",
                    "status": "open",
                    "customerName": "Ada Lovelace",
                    "latestNote": "Awaiting callback scheduling.",
                    "risk": "medium",
                    "decision": "",
                },
            },
            "notes": {},
            "customerSummaries": {},
            "policyEvidence": [],
        }

        for required in test.get("requiredTools") or []:
            assertions.append(assertion(f"required tool {required}", has_tool(executed_tools, str(required)), True, executed_tools))
        any_tools = [str(item) for item in test.get("requiredAnyTools") or []]
        if any_tools:
            assertions.append(assertion("one required tool available", any(has_tool(executed_tools, item) for item in any_tools), any_tools, executed_tools))

        if test_type == "autoclaims_claim_status":
            claim_id = str(test.get("claimId") or "CLM-1001")
            has_claim_arg = has_call_arg(solution, "autoclaims.api.getclaim", ["claimId", "claim_id", "id"], claim_id)
            assertions.append(assertion("get claim argument", has_claim_arg, claim_id, [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.getclaim")]))
            actual = state["claims"].get(claim_id, {}) if has_claim_arg else {}
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            assertions.extend(
                [
                    assertion("claim status", actual.get("status") == expected.get("status"), expected.get("status"), actual.get("status")),
                    assertion("customer name", actual.get("customerName") == expected.get("customerName"), expected.get("customerName"), actual.get("customerName")),
                    assertion(
                        "latest note",
                        str(expected.get("latestNoteContains") or "").lower() in str(actual.get("latestNote") or "").lower(),
                        expected.get("latestNoteContains"),
                        actual.get("latestNote"),
                    ),
                ]
            )
        elif test_type == "autoclaims_decision":
            claim_id = str(test.get("claimId") or "")
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            has_get_claim_arg = has_call_arg(solution, "autoclaims.api.getclaim", ["claimId", "claim_id", "id"], claim_id)
            has_decision_claim_arg = has_call_arg(solution, "autoclaims.api.setclaimdecision", ["claimId", "claim_id", "id"], claim_id)
            has_decision_value_arg = has_call_arg(solution, "autoclaims.api.setclaimdecision", ["decision", "status"], str(expected.get("decision") or ""))
            policy_term = str(expected.get("policyContains") or "policy")
            policy_checked = has_call_arg_containing(solution, "knowledge.company_docs.search", ["query", "q"], policy_term)
            assertions.extend(
                [
                    assertion("get claim argument", has_get_claim_arg, claim_id, [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.getclaim")]),
                    assertion("decision claim argument", has_decision_claim_arg, claim_id, [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.setclaimdecision")]),
                    assertion("decision value argument", has_decision_value_arg, expected.get("decision"), [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.setclaimdecision")]),
                    assertion("policy query argument", policy_checked, policy_term, [call_arguments(call) for call in matching_tool_calls(solution, "knowledge.company_docs.search")]),
                ]
            )
            if policy_checked:
                state["policyEvidence"].append(str(expected.get("policyContains") or "policy"))
            if has_get_claim_arg and has_decision_claim_arg and has_decision_value_arg:
                claim = state["claims"].get(claim_id)
                if claim:
                    claim["decision"] = expected.get("decision")
                    claim["status"] = expected.get("decision")
            actual = state["claims"].get(claim_id, {})
            assertions.extend(
                [
                    assertion("policy checked", policy_checked, True, policy_checked),
                    assertion("decision set", actual.get("decision") == expected.get("decision"), expected.get("decision"), actual.get("decision")),
                    assertion(
                        "policy evidence",
                        str(expected.get("policyContains") or "").lower() in " ".join(state["policyEvidence"]).lower(),
                        expected.get("policyContains"),
                        state["policyEvidence"],
                    ),
                ]
            )
        elif test_type == "autoclaims_claim_note":
            claim_id = str(test.get("claimId") or "CLM-3003")
            has_api_claim_arg = has_call_arg(solution, "autoclaims.api.addclaimnote", ["claimId", "claim_id", "id"], claim_id)
            has_web_claim_arg = has_call_arg_containing(solution, "autoclaims.web.explore_workflows", ["goal", "intent", "task", "description"], claim_id)
            assertions.append(
                assertion(
                    "claim note target",
                    has_api_claim_arg or has_web_claim_arg,
                    claim_id,
                    {
                        "api": [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.addclaimnote")],
                        "web": [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.web.explore_workflows")],
                    },
                )
            )
            if has_api_claim_arg or has_web_claim_arg:
                state["notes"][claim_id] = ["Customer requested a same-day callback."]
            note_text = " ".join(state["notes"].get(claim_id, []))
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            assertions.append(
                assertion("claim note", str(expected.get("noteContains") or "").lower() in note_text.lower(), expected.get("noteContains"), note_text)
            )
        elif test_type == "autoclaims_customer_summary":
            customer = str(test.get("customerName") or "Ada Lovelace")
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            has_customer_query = has_call_arg_containing(solution, "autoclaims.api.searchcustomers", ["query", "q", "name"], customer)
            has_claims_call = bool(matching_tool_calls(solution, "autoclaims.api.listclaims"))
            has_policy_query = has_call_arg_containing(solution, "knowledge.company_docs.search", ["query", "q"], "next")
            assertions.extend(
                [
                    assertion("customer search argument", has_customer_query, customer, [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.searchcustomers")]),
                    assertion("list claims call", has_claims_call, True, [call_arguments(call) for call in matching_tool_calls(solution, "autoclaims.api.listclaims")]),
                    assertion("next actions policy query", has_policy_query, "next", [call_arguments(call) for call in matching_tool_calls(solution, "knowledge.company_docs.search")]),
                ]
            )
            if (
                has_customer_query
                and has_claims_call
                and has_policy_query
            ):
                open_claims = [claim for claim in state["claims"].values() if claim.get("customerName") == customer and claim.get("status") == "open"]
                state["customerSummaries"][customer] = {
                    "openClaimCount": len(open_claims),
                    "summary": "Ada Lovelace has open claims with next actions from the claims policy.",
                }
            summary = state["customerSummaries"].get(customer, {})
            assertions.extend(
                [
                    assertion("open claim count", summary.get("openClaimCount") == expected.get("openClaimCount"), expected.get("openClaimCount"), summary.get("openClaimCount")),
                    assertion(
                        "summary content",
                        str(expected.get("summaryContains") or "").lower() in str(summary.get("summary") or "").lower(),
                        expected.get("summaryContains"),
                        summary.get("summary"),
                    ),
                ]
            )
        else:
            assertions.append(assertion("known execution test", False, "known test type", test_type))

        passed = bool(assertions) and all(item.get("passed") for item in assertions)
        score = round(sum(1 for item in assertions if item.get("passed")) / len(assertions), 4) if assertions else 0.0
        return IcaAgentExecutionTaskResult(
            taskId=task.taskId,
            passed=passed,
            score=score,
            agentId=agent.agentId,
            executedTools=executed_tools,
            assertions=assertions,
            state=state,
        )


class AutoPricingExecutor:
    project_id = "autopricing"

    def run_task(
        self,
        *,
        task: Any,
        solution: IcaTaskSolutionSpec,
        agent: AgentConfig,
    ) -> IcaAgentExecutionTaskResult:
        test = task.metadata.get("executionTest") if isinstance(task.metadata.get("executionTest"), dict) else {}
        test_type = str(test.get("type") or "")
        executed_tools = executed_tool_names(solution)
        assertions: list[dict[str, Any]] = []
        state: dict[str, Any] = {"quotes": {}}

        for required in test.get("requiredTools") or []:
            assertions.append(assertion(f"required tool {required}", has_tool(executed_tools, str(required)), True, executed_tools))

        if test_type == "autopricing_discount_quote":
            expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
            if has_tool(executed_tools, "autopricing.code.inspect"):
                state["quotes"]["ACME"] = {
                    "discountPercent": 18,
                    "approvalRequired": False,
                    "rationale": "Enterprise renewal with 120 seats and 18 month term qualifies for the strategic enterprise discount.",
                }
            quote = state["quotes"].get("ACME", {})
            assertions.extend(
                [
                    assertion("discount percent", quote.get("discountPercent") == expected.get("discountPercent"), expected.get("discountPercent"), quote.get("discountPercent")),
                    assertion("approval required", quote.get("approvalRequired") == expected.get("approvalRequired"), expected.get("approvalRequired"), quote.get("approvalRequired")),
                    assertion(
                        "rationale",
                        str(expected.get("rationaleContains") or "").lower() in str(quote.get("rationale") or "").lower(),
                        expected.get("rationaleContains"),
                        quote.get("rationale"),
                    ),
                ]
            )
        else:
            assertions.append(assertion("known execution test", False, "known test type", test_type))

        passed = bool(assertions) and all(item.get("passed") for item in assertions)
        score = round(sum(1 for item in assertions if item.get("passed")) / len(assertions), 4) if assertions else 0.0
        return IcaAgentExecutionTaskResult(
            taskId=task.taskId,
            passed=passed,
            score=score,
            agentId=agent.agentId,
            executedTools=executed_tools,
            assertions=assertions,
            state=state,
        )


class LegacyIwaWebExecutor:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def run_task(
        self,
        *,
        task: Any,
        solution: IcaTaskSolutionSpec,
        agent: AgentConfig,
    ) -> IcaAgentExecutionTaskResult:
        test = task.metadata.get("executionTest") if isinstance(task.metadata.get("executionTest"), dict) else {}
        iwa_project = str(test.get("projectId") or task.metadata.get("legacyIwaProject") or "")
        use_case = str(test.get("useCase") or task.metadata.get("iwaUseCase") or "")
        expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
        expected_event = str(expected.get("eventName") or use_case)
        expected_criteria = expected.get("eventCriteria") if isinstance(expected.get("eventCriteria"), dict) else {}
        executed_tools = executed_tool_names(solution)
        browser_tool = f"{self.project_id}.web.explore_workflows"
        assertions: list[dict[str, Any]] = []

        assertions.append(assertion(f"required tool {browser_tool}", has_tool(executed_tools, browser_tool), True, executed_tools))
        expected_tests = iwa_tests(iwa_project, use_case)
        assertions.append(assertion("iwa use case has tests", bool(expected_tests), True, {"projectId": iwa_project, "useCase": use_case}))

        browser_calls = matching_tool_calls(solution, browser_tool)
        browser_args = [call_arguments(call) for call in browser_calls]
        goal_values = [
            args.get(key)
            for args in browser_args
            for key in ("goal", "intent", "task", "description", "query", "targetView", "title")
            if args.get(key)
        ]
        expected_goal_text = " ".join(
            str(part or "")
            for part in (
                getattr(task, "name", ""),
                getattr(task, "prompt", ""),
                getattr(task, "successCriteria", ""),
                expected_criteria,
            )
        )
        has_goal_match = semantic_goal_match(expected_goal_text, goal_values)
        has_use_case = any(
            use_case.lower() in str(args.get(key) or "").lower()
            for args in browser_args
            for key in ("useCase", "use_case", "iwaUseCase", "eventName", "goal", "intent", "task", "description")
        )
        has_event_name = any(
            expected_event.lower() in str(args.get(key) or "").lower()
            for args in browser_args
            for key in ("eventName", "useCase", "use_case", "iwaUseCase", "goal", "intent", "task", "description")
        )
        has_expected_criteria = True
        for key, value in expected_criteria.items():
            if not any(str(value).lower() in str(args.get(key) or args).lower() for args in browser_args):
                has_expected_criteria = False
                break

        assertions.extend(
            [
                assertion("web goal matches expected task", has_goal_match or has_use_case or has_event_name, expected_goal_text, browser_args),
                assertion("iwa criteria target", has_expected_criteria, expected_criteria, browser_args),
            ]
        )
        state = {
            "iwaProjectId": iwa_project,
            "iwaUseCase": use_case,
            "expectedEvent": expected_event,
            "expectedTests": expected_tests,
            "browserArguments": browser_args,
        }
        passed = bool(assertions) and all(item.get("passed") for item in assertions)
        score = round(sum(1 for item in assertions if item.get("passed")) / len(assertions), 4) if assertions else 0.0
        return IcaAgentExecutionTaskResult(
            taskId=task.taskId,
            passed=passed,
            score=score,
            agentId=agent.agentId,
            executedTools=executed_tools,
            assertions=assertions,
            state=state,
        )


_EXECUTORS: dict[str, DemoCompanyExecutor] = {
    AutoCommerceExecutor.project_id: AutoCommerceExecutor(),
    AutoClaimsExecutor.project_id: AutoClaimsExecutor(),
    AutoPricingExecutor.project_id: AutoPricingExecutor(),
    "autocalendar_web": LegacyIwaWebExecutor("autocalendar_web"),
}


def get_demo_company_executor(project_id: str) -> DemoCompanyExecutor | None:
    executor = _EXECUTORS.get(project_id)
    if executor is not None:
        return executor
    if project_id.endswith("_web"):
        legacy_project_id = project_id[:-4]
        if load_iwa_trajectory_map(legacy_project_id):
            return LegacyIwaWebExecutor(project_id)
    return None


def list_demo_company_executor_ids() -> list[str]:
    return sorted(_EXECUTORS)
