import json
import os
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pymongo import ReturnDocument
from pydantic import BaseModel, Field, field_validator

from app.database import agents_collection, work_boards_collection, work_items_collection
from app.repositories import WorkBoardRepository, WorkItemRepository
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.routes.notifications import create_notification
from app.services.agent_runtime import agent_step_result
from app.services.metering import run_credits_spent
from app.services.queue import enqueue_job
from app.services.trajectory_judges import list_trajectory_judges

router = APIRouter()

WorkStatus = Literal["TODO", "RUNNING", "REVIEW", "DONE", "FAILED"]
RunTarget = Literal["selected", "all"]
TriggerType = Literal["manual", "scheduled"]
ScheduleFrequency = Literal["none", "daily", "weekly"]


def _normalize_work_status(value: Any) -> Any:
    if isinstance(value, str) and value.upper() == "BACKLOG":
        return "TODO"
    return value


class WorkBoardCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    name: str


class WorkBoardUpdateRequest(BaseModel):
    name: str | None = None


class WorkItemCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    boardId: str = ""
    title: str
    prompt: str
    successCriteria: str = ""
    agentId: str = ""
    agentName: str = ""
    runTarget: RunTarget = "all"
    browserEnabled: bool = True
    browserMode: Literal["visible", "headless"] = "headless"
    maxCreditsPerRun: float = 5.0
    maxBudgetCredits: float | None = None
    maxSteps: int = 8
    triggerType: TriggerType = "manual"
    scheduleFrequency: ScheduleFrequency = "none"
    scheduleTime: str = "09:00"
    scheduleDayOfWeek: int = 1
    triggerConfig: dict[str, Any] = Field(default_factory=dict)
    sourceTaskId: str = ""
    sourceBenchmarkId: str = ""
    judgeImplementation: str = "llm"
    status: WorkStatus = "TODO"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        return _normalize_work_status(value)


class WorkItemUpdateRequest(BaseModel):
    title: str | None = None
    prompt: str | None = None
    successCriteria: str | None = None
    boardId: str | None = None
    agentId: str | None = None
    agentName: str | None = None
    runTarget: RunTarget | None = None
    browserEnabled: bool | None = None
    browserMode: Literal["visible", "headless"] | None = None
    maxCreditsPerRun: float | None = None
    maxBudgetCredits: float | None = None
    maxSteps: int | None = None
    triggerType: TriggerType | None = None
    scheduleFrequency: ScheduleFrequency | None = None
    scheduleTime: str | None = None
    scheduleDayOfWeek: int | None = None
    triggerConfig: dict[str, Any] | None = None
    sourceTaskId: str | None = None
    sourceBenchmarkId: str | None = None
    judgeImplementation: str | None = None
    status: WorkStatus | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        return _normalize_work_status(value)


class WorkItemRunRequest(BaseModel):
    browserEnabled: bool | None = None
    browserMode: Literal["visible", "headless"] | None = None
    maxCreditsPerRun: float | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_schedule_time(value: str) -> time:
    try:
        hour, minute = str(value or "09:00").split(":", 1)
        return time(hour=max(0, min(23, int(hour))), minute=max(0, min(59, int(minute))), tzinfo=timezone.utc)
    except Exception:
        return time(hour=9, minute=0, tzinfo=timezone.utc)


def _next_run_at(*, frequency: str, schedule_time: str, day_of_week: int = 1, from_dt: datetime | None = None) -> str:
    if frequency not in {"daily", "weekly"}:
        return ""
    base = from_dt or datetime.now(timezone.utc)
    target_time = _parse_schedule_time(schedule_time)
    candidate = datetime.combine(base.date(), target_time, tzinfo=timezone.utc)
    if frequency == "daily":
        if candidate <= base:
            candidate += timedelta(days=1)
        return candidate.isoformat()

    normalized_day = max(0, min(6, int(day_of_week or 0)))
    days_ahead = (normalized_day - candidate.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= base:
        candidate += timedelta(days=7)
    return candidate.isoformat()


def _serialize_board(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "boardId": doc.get("boardId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "name": doc.get("name", "Work Board"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _default_board(email: str, company_id: str = "") -> dict[str, Any]:
    existing = await work_boards_collection.find_one({"email": email, "companyId": company_id, "name": "Default"}, {"_id": 0})
    if existing:
        return existing
    now = _now()
    doc = {"boardId": str(uuid.uuid4()), "email": email, "companyId": company_id, "name": "Default", "createdAt": now, "updatedAt": now}
    await work_boards_collection.insert_one(doc)
    return doc


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "workItemId": doc.get("workItemId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "boardId": doc.get("boardId", ""),
        "title": doc.get("title", ""),
        "prompt": doc.get("prompt", ""),
        "successCriteria": doc.get("successCriteria", ""),
        "agentId": doc.get("agentId", ""),
        "agentName": doc.get("agentName", ""),
        "runTarget": doc.get("runTarget", "selected"),
        "browserEnabled": bool(doc.get("browserEnabled", True)),
        "browserMode": doc.get("browserMode", "headless"),
        "maxCreditsPerRun": float(doc.get("maxCreditsPerRun", 5.0) or 0.0),
        "maxBudgetCredits": float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun", 5.0)) or 0.0),
        "maxSteps": int(doc.get("maxSteps", 8) or 8),
        "triggerType": doc.get("triggerType", "manual"),
        "scheduleFrequency": doc.get("scheduleFrequency", "none"),
        "scheduleTime": doc.get("scheduleTime", "09:00"),
        "scheduleDayOfWeek": int(doc.get("scheduleDayOfWeek", 1) or 0),
        "nextRunAt": doc.get("nextRunAt", ""),
        "triggerConfig": doc.get("triggerConfig") if isinstance(doc.get("triggerConfig"), dict) else {},
        "sourceTaskId": doc.get("sourceTaskId", ""),
        "sourceBenchmarkId": doc.get("sourceBenchmarkId", ""),
        "judgeImplementation": doc.get("judgeImplementation", "llm"),
        "status": doc.get("status", "TODO"),
        "report": doc.get("report") or {},
        "judge": doc.get("judge") or {},
        "runHistory": doc.get("runHistory") or [],
        "lastRunId": doc.get("lastRunId", ""),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
        "startedAt": doc.get("startedAt", ""),
        "completedAt": doc.get("completedAt", ""),
    }


def _deterministic_judge_result(results: list[dict[str, Any]], success_criteria: str = "") -> dict[str, Any]:
    ok_results = [item for item in results if item.get("status") == "ok"]
    failed_results = [item for item in results if item.get("status") in {"failed", "budget_exhausted"}]
    completed = [
        item
        for item in ok_results
        if isinstance(item.get("result"), dict)
        and (item["result"].get("done") is True or item["result"].get("content") or item["result"].get("tool_calls"))
    ]
    if completed and not failed_results:
        label = "success"
        reason = "All selected agents returned a usable runtime result."
    elif completed:
        label = "needs_review"
        reason = "At least one agent returned a usable result, but another failed."
    else:
        label = "failed"
        reason = "No selected agent returned a usable runtime result."
    if success_criteria.strip():
        reason = f"{reason} Success criteria still needs review: {success_criteria.strip()}"
    return {"label": label, "reason": reason, "judgeType": "deterministic_runtime_result"}


async def _judge_result(item: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = _deterministic_judge_result(results, str(item.get("successCriteria") or ""))
    judge_name = str(item.get("judgeImplementation") or "llm").strip().lower()
    if judge_name in {"deterministic", "deterministic_runtime_result", "rules"}:
        return {**fallback, "judgeType": judge_name}
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {**fallback, "judgeType": "llm_judge_unavailable:no_openai_api_key"}

    from openai import AsyncOpenAI

    payload = {
        "title": item.get("title", ""),
        "prompt": item.get("prompt", ""),
        "successCriteria": item.get("successCriteria", ""),
        "runTarget": item.get("runTarget", "selected"),
        "browserEnabled": bool(item.get("browserEnabled", True)),
        "judgeImplementation": judge_name,
        "results": results,
        "fallback": fallback,
    }
    prompt = (
        "You are Automata Work LLMJudge. Decide whether this autonomous work item succeeded. "
        "Use the work prompt, success criteria, agent runtime results, tool calls, content, and errors. "
        "Return strict JSON with label success|failed|needs_review, confidence 0-1, reason string.\n\n"
        f"Work report:\n{json.dumps(payload, ensure_ascii=False)[:16000]}"
    )
    try:
        client = AsyncOpenAI(api_key=api_key)
        model = os.getenv("AUTOMATA_WORK_JUDGE_MODEL", os.getenv("AUTOMATA_EVAL_JUDGE_MODEL", "gpt-5-mini"))
        response = await client.responses.create(
            model=model,
            input=prompt,
            text={"format": {"type": "json_object"}},
        )
        data = json.loads(response.output_text)
    except Exception as exc:
        return {**fallback, "judgeType": "llm_judge_failed", "llmError": str(exc)}

    label = str(data.get("label") or "needs_review").lower()
    if label not in {"success", "failed", "needs_review"}:
        label = "needs_review"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "label": label,
        "confidence": confidence,
        "reason": str(data.get("reason") or data.get("reasoning") or fallback["reason"]),
        "judgeType": model,
        "fallback": fallback,
    }


async def _agent_docs_for_work(item: dict[str, Any]) -> list[dict[str, Any]]:
    if item.get("runTarget") == "all":
        query: dict[str, Any] = {"email": item.get("email", "")}
        if item.get("companyId"):
            query["companyId"] = item["companyId"]
        return await agents_collection.find(query, {"_id": 0}).sort("createdAt", -1).to_list(length=12)

    agent_id = str(item.get("agentId") or "")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required for selected work items")
    doc = await agents_collection.find_one({"agentId": agent_id, "email": item.get("email", "")}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Agent not found")
    return [doc]


def _is_executable_browser_call(call: dict[str, Any]) -> bool:
    name = str(call.get("name") or call.get("action") or "")
    return name.startswith("browser.") and name not in {"browser.done", "browser.screenshot", "browser.snapshot", "browser.extract"}


def _deep_merge_state(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_state(merged[key], value)
        else:
            merged[key] = value
    return merged


async def _run_agent_work_steps(item: dict[str, Any], doc: dict[str, Any], run_id: str) -> dict[str, Any]:
    agent_id = str(doc.get("agentId") or "")
    browser_enabled = bool(item.get("browserEnabled", True))
    max_steps = max(1, min(30, int(item.get("maxSteps", 8) or 8)))
    runtime_budget = max(0.0, float(item.get("maxBudgetCredits", item.get("maxCreditsPerRun", 0.0)) or 0.0))
    raw_pending_resume = item.get("pendingApproval") if isinstance(item.get("pendingApproval"), dict) else {}
    pending_resume = raw_pending_resume if str(raw_pending_resume.get("agentId") or "") in {"", agent_id} else {}
    state: dict[str, Any] = pending_resume.get("state") if isinstance(pending_resume.get("state"), dict) else {}
    state_patch = pending_resume.get("statePatch") if isinstance(pending_resume.get("statePatch"), dict) else {}
    if state_patch:
        state = _deep_merge_state(state, state_patch)
    if pending_resume.get("approvalKey"):
        approved = set(state.get("approvedConnectorToolCalls") or [])
        approved.add(str(pending_resume.get("approvalKey") or ""))
        state["approvedConnectorToolCalls"] = list(approved)
    steps: list[dict[str, Any]] = []
    final_result: dict[str, Any] = {}
    current_url = str(pending_resume.get("currentUrl") or doc.get("websiteUrl") or "")
    browser = None

    try:
        if browser_enabled:
            from agent.browser_executor import BrowserExecutor

            browser_mode = "local_headful" if str(item.get("browserMode") or "headless") == "visible" else "headless"
            browser = BrowserExecutor()
            await browser.initialize(initial_url=current_url or None, browser_mode=browser_mode)
            current_url = browser.get_current_url()

        for step_index in range(max_steps):
            if runtime_budget > 0:
                spent = await run_credits_spent(run_id)
                if spent >= runtime_budget:
                    final_result = {
                        "done": True,
                        "content": f"Run stopped after spending {spent:.2f}/{runtime_budget:.2f} credits.",
                        "state_out": state,
                    }
                    return {
                        "agentId": agent_id,
                        "agentName": doc.get("name", ""),
                        "status": "budget_exhausted",
                        "result": final_result,
                        "steps": steps,
                        "finalUrl": current_url,
                        "stepCount": len(steps),
                        "creditsSpent": spent,
                        "maxBudgetCredits": runtime_budget,
                    }
            result = await agent_step_result(
                agent_id,
                {
                    "prompt": item.get("prompt", ""),
                    "task": item.get("prompt", ""),
                    "url": current_url,
                    "step_index": step_index,
                    "state_in": state,
                    "context": {
                        "runtimeOverrides": {
                            "browserEnabled": browser_enabled,
                            "browserMode": item.get("browserMode", "headless"),
                            "maxCreditsPerRun": runtime_budget,
                        },
                        "workItemId": item.get("workItemId"),
                        "runId": run_id,
                    },
                },
            )
            final_result = result if isinstance(result, dict) else {"raw": result}
            state = final_result.get("state_out") if isinstance(final_result.get("state_out"), dict) else state
            tool_calls = final_result.get("tool_calls") if isinstance(final_result.get("tool_calls"), list) else []
            step_record: dict[str, Any] = {
                "stepIndex": step_index,
                "toolCalls": tool_calls,
                "content": final_result.get("content"),
                "reasoning": final_result.get("reasoning"),
                "done": bool(final_result.get("done")),
            }

            if browser and tool_calls:
                executed = []
                for call in tool_calls:
                    if not isinstance(call, dict) or not _is_executable_browser_call(call):
                        continue
                    try:
                        from agent.autoppia_agent import _execute_tool_call

                        await _execute_tool_call(browser.page, call)
                        current_url = browser.get_current_url()
                        executed.append({"name": call.get("name"), "success": True})
                    except Exception as exc:
                        executed.append({"name": call.get("name"), "success": False, "error": str(exc)})
                if executed:
                    step_record["executed"] = executed
                    step_record["url"] = current_url

            last_tool_results = list(final_result.get("tool_results") or []) if isinstance(final_result.get("tool_results"), list) else []
            if step_record.get("executed"):
                last_tool_results.extend(
                    {
                        "tool": item.get("name", ""),
                        "success": bool(item.get("success")),
                        **({"error": item.get("error")} if item.get("error") else {}),
                    }
                    for item in step_record["executed"]
                    if isinstance(item, dict)
                )
            if last_tool_results:
                state = {**state, "automata_last_tool_results": last_tool_results}
                step_record["toolResults"] = last_tool_results

            steps.append(step_record)
            approval_call = next(
                (
                    call
                    for call in tool_calls
                    if isinstance(call, dict)
                    and str(call.get("name") or "") == "api.human_approval"
                    and isinstance(call.get("arguments"), dict)
                ),
                None,
            )
            if approval_call:
                approval_args = approval_call.get("arguments") or {}
                return {
                    "agentId": agent_id,
                    "agentName": doc.get("name", ""),
                    "status": "waiting_approval",
                    "result": final_result,
                    "steps": steps,
                    "finalUrl": current_url,
                    "stepCount": len(steps),
                    "pendingApproval": {
                        "approvalId": str(approval_args.get("approvalId") or ""),
                        "approvalKey": str(approval_args.get("approvalKey") or ""),
                        "proposedAction": approval_args.get("proposedAction") if isinstance(approval_args.get("proposedAction"), dict) else {},
                        "state": state,
                        "statePatch": approval_args.get("statePatch") if isinstance(approval_args.get("statePatch"), dict) else {},
                        "stepIndex": step_index,
                        "currentUrl": current_url,
                        "agentId": agent_id,
                    },
                }
            if final_result.get("done") is True:
                break
            if not tool_calls and final_result.get("content"):
                break

        return {
            "agentId": agent_id,
            "agentName": doc.get("name", ""),
            "status": "ok",
            "result": final_result,
            "steps": steps,
            "finalUrl": current_url,
            "stepCount": len(steps),
        }
    except Exception as exc:
        return {
            "agentId": agent_id,
            "agentName": doc.get("name", ""),
            "status": "failed",
            "error": str(getattr(exc, "detail", exc)),
            "steps": steps,
            "finalUrl": current_url,
            "stepCount": len(steps),
        }
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


async def _run_work_item(work_item_id: str, run_id: str) -> None:
    item = await work_items_collection.find_one({"workItemId": work_item_id}, {"_id": 0})
    if not item:
        return

    results: list[dict[str, Any]] = []
    try:
        docs = await _agent_docs_for_work(item)
        if not docs:
            raise HTTPException(status_code=404, detail="No agents found")

        for doc in docs:
            results.append(await _run_agent_work_steps(item, doc, run_id))

        waiting = next((result for result in results if result.get("status") == "waiting_approval"), None)
        if waiting:
            pending = waiting.get("pendingApproval") if isinstance(waiting.get("pendingApproval"), dict) else {}
            await work_items_collection.update_one(
                {"workItemId": work_item_id},
                {
                    "$set": {
                        "status": "REVIEW",
                        "report": {
                            "runId": run_id,
                            "target": item.get("runTarget", "selected"),
                            "resultCount": len(results),
                            "results": results,
                            "summary": "Waiting for human approval before continuing.",
                        },
                        "pendingApproval": {**pending, "status": "pending", "runId": run_id, "updatedAt": _now()},
                        "updatedAt": _now(),
                    },
                    "$push": {"runHistory": {"runId": run_id, "status": "WAITING_APPROVAL", "createdAt": _now(), "approvalId": pending.get("approvalId", "")}},
                },
            )
            await _notify_work_item(
                item,
                title="Work item waiting for approval",
                message=f"{item.get('title', 'Work item')} needs approval before continuing.",
                level="warning",
                run_id=run_id,
                status="REVIEW",
            )
            return

        judge = await _judge_result(item, results)
        next_status = "DONE" if judge["label"] == "success" else "REVIEW" if judge["label"] == "needs_review" else "FAILED"
        report = {
            "runId": run_id,
            "target": item.get("runTarget", "selected"),
            "resultCount": len(results),
            "results": results,
            "summary": judge["reason"],
        }
        await work_items_collection.update_one(
            {"workItemId": work_item_id},
            {
                "$set": {
                    "status": next_status,
                    "report": report,
                    "judge": judge,
                    "pendingApproval": {},
                    "nextRunAt": _next_run_at(
                        frequency=str(item.get("scheduleFrequency") or "none"),
                        schedule_time=str(item.get("scheduleTime") or "09:00"),
                        day_of_week=int(item.get("scheduleDayOfWeek") or 1),
                    ) if item.get("triggerType") == "scheduled" else "",
                    "completedAt": _now(),
                    "updatedAt": _now(),
                },
                "$push": {"runHistory": {"runId": run_id, "status": next_status, "judge": judge, "createdAt": _now()}},
            },
        )
        await _notify_work_item(
            item,
            title=f"Work item {next_status.lower()}",
            message=f"{item.get('title', 'Work item')} finished with judge result: {judge['label']}.",
            level="success" if next_status == "DONE" else "warning" if next_status == "REVIEW" else "error",
            run_id=run_id,
            status=next_status,
        )
    except Exception as exc:
        judge = {"label": "failed", "reason": str(getattr(exc, "detail", exc)), "judgeType": "deterministic_runtime_result"}
        await work_items_collection.update_one(
            {"workItemId": work_item_id},
            {
                "$set": {
                    "status": "FAILED",
                    "report": {"runId": run_id, "results": results, "summary": judge["reason"]},
                    "judge": judge,
                    "nextRunAt": _next_run_at(
                        frequency=str(item.get("scheduleFrequency") or "none"),
                        schedule_time=str(item.get("scheduleTime") or "09:00"),
                        day_of_week=int(item.get("scheduleDayOfWeek") or 1),
                    ) if item.get("triggerType") == "scheduled" else "",
                    "completedAt": _now(),
                    "updatedAt": _now(),
                },
                "$push": {"runHistory": {"runId": run_id, "status": "FAILED", "judge": judge, "createdAt": _now()}},
            },
        )
        await _notify_work_item(
            item,
            title="Work item failed",
            message=f"{item.get('title', 'Work item')} failed: {judge['reason']}",
            level="error",
            run_id=run_id,
            status="FAILED",
        )


async def _notify_work_item(
    item: dict[str, Any],
    *,
    title: str,
    message: str,
    level: Literal["info", "success", "warning", "error"] = "info",
    run_id: str = "",
    status: str = "",
) -> None:
    try:
        await create_notification(
            email=str(item.get("email") or ""),
            company_id=str(item.get("companyId") or ""),
            title=title,
            message=message,
            level=level,
            source="work",
            entity_type="work_item",
            entity_id=str(item.get("workItemId") or ""),
            action_url=f"/work?item={item.get('workItemId')}",
            metadata={"runId": run_id, "status": status, "boardId": item.get("boardId", "")},
        )
    except Exception:
        pass


@router.get("/work-judges")
async def list_work_judges():
    base = [
        {"name": "llm", "label": "LLMJudge", "description": "OpenAI LLMJudge over the work report."},
        {"name": "deterministic_runtime_result", "label": "Deterministic", "description": "Checks runtime result/tool output without LLM spend."},
    ]
    seen = {item["name"] for item in base}
    extra = [item for item in list_trajectory_judges() if item.get("name") not in seen]
    return {
        "judges": [*base, *extra]
    }


@router.get("/work-boards")
async def list_work_boards(email: str, companyId: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(email)
    await _default_board(email, companyId)
    query: dict[str, Any] = {"email": email}
    if companyId:
        query["companyId"] = companyId
    docs = await work_boards_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=100)
    return {"boards": [_serialize_board(doc) for doc in docs]}


@router.post("/work-boards")
async def create_work_board(body: WorkBoardCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    now = _now()
    doc = {"boardId": str(uuid.uuid4()), "email": email, "companyId": body.companyId, "name": body.name.strip(), "createdAt": now, "updatedAt": now}
    await work_boards_collection.insert_one(doc)
    return {"success": True, "board": _serialize_board(doc)}


@router.patch("/work-boards/{board_id}")
async def update_work_board(board_id: str, body: WorkBoardUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    repo = _board_repo(scope)
    existing = await repo.by_id(board_id)
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if "name" in updates:
        updates["name"] = str(updates["name"]).strip()
    updates["updatedAt"] = _now()
    refreshed = await repo.update_owned_one({"boardId": board_id}, {"$set": updates}, not_found="Work board not found")
    return {"success": True, "board": _serialize_board(refreshed or existing)}


@router.delete("/work-boards/{board_id}")
async def delete_work_board(board_id: str, scope: RequestScope = Depends(get_request_scope)):
    board = await _board_repo(scope).by_id(board_id)
    await work_items_collection.update_many({"boardId": board_id}, {"$set": {"boardId": "", "updatedAt": _now()}})
    result = await work_boards_collection.delete_one({"boardId": board_id, "email": board.get("email", "")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Work board not found")
    return {"success": True}


@router.get("/work-items")
async def list_work_items(email: str, companyId: str = "", boardId: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(email)
    board = await _default_board(email, companyId)
    query: dict[str, Any] = {"email": email}
    if companyId:
        query["companyId"] = companyId
    if boardId:
        query["boardId"] = boardId
    elif board.get("boardId"):
        query["$or"] = [{"boardId": board["boardId"]}, {"boardId": {"$exists": False}}, {"boardId": ""}]
    docs = await work_items_collection.find(query, {"_id": 0}).sort("createdAt", -1).to_list(length=500)
    return {"workItems": [_serialize(doc) for doc in docs]}


@router.post("/work-items")
async def create_work_item(body: WorkItemCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    if not body.title.strip() or not body.prompt.strip():
        raise HTTPException(status_code=400, detail="title and prompt are required")
    now = _now()
    board_id = body.boardId or (await _default_board(email, body.companyId)).get("boardId", "")
    max_budget = body.maxBudgetCredits if body.maxBudgetCredits is not None else body.maxCreditsPerRun
    next_run_at = _next_run_at(
        frequency=body.scheduleFrequency,
        schedule_time=body.scheduleTime,
        day_of_week=body.scheduleDayOfWeek,
    ) if body.triggerType == "scheduled" else ""
    doc = {
        "workItemId": str(uuid.uuid4()),
        "email": email,
        "companyId": body.companyId,
        "boardId": board_id,
        "title": body.title.strip(),
        "prompt": body.prompt.strip(),
        "successCriteria": body.successCriteria.strip(),
        "agentId": body.agentId,
        "agentName": body.agentName,
        "runTarget": body.runTarget,
        "browserEnabled": body.browserEnabled,
        "browserMode": body.browserMode,
        "maxCreditsPerRun": max(0.0, float(body.maxCreditsPerRun or 0.0)),
        "maxBudgetCredits": max(0.0, float(max_budget or 0.0)),
        "maxSteps": max(1, min(30, int(body.maxSteps or 8))),
        "triggerType": body.triggerType,
        "scheduleFrequency": body.scheduleFrequency,
        "scheduleTime": body.scheduleTime,
        "scheduleDayOfWeek": body.scheduleDayOfWeek,
        "nextRunAt": next_run_at,
        "triggerConfig": body.triggerConfig,
        "sourceTaskId": body.sourceTaskId,
        "sourceBenchmarkId": body.sourceBenchmarkId,
        "judgeImplementation": body.judgeImplementation,
        "status": body.status,
        "report": {},
        "judge": {},
        "runHistory": [],
        "createdAt": now,
        "updatedAt": now,
    }
    await work_items_collection.insert_one(doc)
    return {"success": True, "workItem": _serialize(doc)}


@router.patch("/work-items/{work_item_id}")
async def update_work_item(work_item_id: str, body: WorkItemUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    repo = _item_repo(scope)
    existing = await repo.by_id(work_item_id)
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if "title" in updates:
        updates["title"] = str(updates["title"]).strip()
    if "prompt" in updates:
        updates["prompt"] = str(updates["prompt"]).strip()
    if "successCriteria" in updates:
        updates["successCriteria"] = str(updates["successCriteria"]).strip()
    if "maxCreditsPerRun" in updates:
        updates["maxCreditsPerRun"] = max(0.0, float(updates["maxCreditsPerRun"] or 0.0))
    if "maxBudgetCredits" in updates:
        updates["maxBudgetCredits"] = max(0.0, float(updates["maxBudgetCredits"] or 0.0))
    if "maxSteps" in updates:
        updates["maxSteps"] = max(1, min(30, int(updates["maxSteps"] or 8)))
    if "scheduleDayOfWeek" in updates:
        updates["scheduleDayOfWeek"] = max(0, min(6, int(updates["scheduleDayOfWeek"] or 0)))
    if {"triggerType", "scheduleFrequency", "scheduleTime", "scheduleDayOfWeek"} & set(updates.keys()):
        trigger_type = updates.get("triggerType", existing.get("triggerType", "manual"))
        frequency = updates.get("scheduleFrequency", existing.get("scheduleFrequency", "none"))
        schedule_time = updates.get("scheduleTime", existing.get("scheduleTime", "09:00"))
        day_of_week = int(updates.get("scheduleDayOfWeek", existing.get("scheduleDayOfWeek", 1)) or 1)
        updates["nextRunAt"] = _next_run_at(frequency=frequency, schedule_time=schedule_time, day_of_week=day_of_week) if trigger_type == "scheduled" else ""
    updates["updatedAt"] = _now()
    refreshed = await repo.update_owned_one({"workItemId": work_item_id}, {"$set": updates}, not_found="Work item not found")
    return {"success": True, "workItem": _serialize(refreshed or existing)}


@router.post("/work-items/{work_item_id}/run")
async def run_work_item(work_item_id: str, body: WorkItemRunRequest = WorkItemRunRequest(), scope: RequestScope = Depends(get_request_scope)):
    repo = _item_repo(scope)
    existing = await repo.by_id(work_item_id)
    if existing.get("status") == "RUNNING":
        raise HTTPException(status_code=409, detail="Work item is already running")

    updates: dict[str, Any] = {"status": "RUNNING", "startedAt": _now(), "completedAt": "", "updatedAt": _now()}
    if body.browserEnabled is not None:
        updates["browserEnabled"] = body.browserEnabled
    if body.browserMode is not None:
        updates["browserMode"] = body.browserMode
    if body.maxCreditsPerRun is not None:
        updates["maxCreditsPerRun"] = max(0.0, float(body.maxCreditsPerRun or 0.0))
        updates["maxBudgetCredits"] = updates["maxCreditsPerRun"]
    run_id = str(uuid.uuid4())
    updates["lastRunId"] = run_id
    await repo.update_owned_one({"workItemId": work_item_id}, {"$set": updates}, not_found="Work item not found")
    await enqueue_job("work_run", {"workItemId": work_item_id, "runId": run_id}, dedupe_key=f"work_run:{work_item_id}:{run_id}")
    refreshed = await work_items_collection.find_one({"workItemId": work_item_id}, {"_id": 0})
    await _notify_work_item(
        refreshed or existing,
        title="Work item started",
        message=f"{(refreshed or existing).get('title', 'Work item')} is running.",
        level="info",
        run_id=run_id,
        status="RUNNING",
    )
    return {"success": True, "runId": run_id, "workItem": _serialize(refreshed or existing)}


@router.post("/work-items/{work_item_id}/rejudge")
async def rejudge_work_item(work_item_id: str, scope: RequestScope = Depends(get_request_scope)):
    repo = _item_repo(scope)
    existing = await repo.by_id(work_item_id)
    report = existing.get("report") if isinstance(existing.get("report"), dict) else {}
    results = report.get("results") if isinstance(report.get("results"), list) else []
    if not results:
        raise HTTPException(status_code=409, detail="Work item has no report results to judge")
    judge = await _judge_result(existing, results)
    next_status = "DONE" if judge["label"] == "success" else "REVIEW" if judge["label"] == "needs_review" else "FAILED"
    await repo.update_owned_one(
        {"workItemId": work_item_id},
        {
            "$set": {
                "status": next_status,
                "judge": judge,
                "report": {**report, "summary": judge["reason"]},
                "updatedAt": _now(),
            },
            "$push": {"runHistory": {"runId": report.get("runId", ""), "status": next_status, "judge": judge, "createdAt": _now(), "rejudge": True}},
        },
    )
    refreshed = await work_items_collection.find_one({"workItemId": work_item_id}, {"_id": 0})
    await _notify_work_item(
        refreshed or existing,
        title="Work item rejudged",
        message=f"{(refreshed or existing).get('title', 'Work item')} is now {next_status.lower()}.",
        level="success" if next_status == "DONE" else "warning" if next_status == "REVIEW" else "error",
        run_id=str(report.get("runId", "")),
        status=next_status,
    )
    return {"success": True, "workItem": _serialize(refreshed or existing), "judge": judge}


@router.delete("/work-items/{work_item_id}")
async def delete_work_item(work_item_id: str, scope: RequestScope = Depends(get_request_scope)):
    deleted = await _item_repo(scope).delete_owned_one({"workItemId": work_item_id}, not_found="Work item not found")
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Work item not found")
    return {"success": True}


async def run_due_scheduled_work_items_once() -> int:
    now = datetime.now(timezone.utc)
    started = 0
    for _ in range(50):
        run_id = str(uuid.uuid4())
        doc = await work_items_collection.find_one_and_update(
            {
                "triggerType": "scheduled",
                "status": {"$ne": "RUNNING"},
                "nextRunAt": {"$lte": now.isoformat(), "$ne": ""},
            },
            {
                "$set": {
                    "status": "RUNNING",
                    "startedAt": _now(),
                    "completedAt": "",
                    "lastRunId": run_id,
                    "updatedAt": _now(),
                }
            },
            projection={"_id": 0},
            sort=[("nextRunAt", 1), ("createdAt", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            break
        await _notify_work_item(
            doc,
            title="Scheduled work started",
            message=f"{doc.get('title', 'Scheduled work item')} started from schedule.",
            level="info",
            run_id=run_id,
            status="RUNNING",
        )
        await enqueue_job("work_run", {"workItemId": str(doc.get("workItemId")), "runId": run_id}, dedupe_key=f"work_run:{doc.get('workItemId')}:{run_id}")
        started += 1
    return started


async def scheduled_work_loop() -> None:
    while True:
        try:
            await run_due_scheduled_work_items_once()
        except Exception:
            pass
        import asyncio

        await asyncio.sleep(60)
def _board_repo(scope: RequestScope) -> WorkBoardRepository:
    return WorkBoardRepository(work_boards_collection, coerce_request_scope(scope))


def _item_repo(scope: RequestScope) -> WorkItemRepository:
    return WorkItemRepository(work_items_collection, coerce_request_scope(scope))
