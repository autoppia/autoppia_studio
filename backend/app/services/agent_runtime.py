from __future__ import annotations

import os
import re
from typing import Any

import httpx
from fastapi import HTTPException

from app.connectors import ConnectorExecutionError, execute_connector_tool
from app.database import agents_collection, capabilities_collection, tools_collection, trajectories_collection
from app.models.agent_config import AgentCallable, AgentConfig
from app.services.observability import record_runtime_event


DEFAULT_BASE_RUNTIME_ENDPOINT = os.getenv("AUTOMATA_DEFAULT_RUNTIME_ENDPOINT", "http://127.0.0.1:5060/step").strip()


def step_url(endpoint: str) -> str:
    clean = endpoint.rstrip("/")
    if not clean:
        return ""
    if clean.endswith("/step"):
        return clean
    return f"{clean}/step"


async def load_agent_config(agent_id: str) -> dict[str, Any]:
    agent = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def serialize_agent(doc: dict[str, Any]) -> dict[str, Any]:
    agent_id = doc.get("agentId", "")
    return {
        "agentId": agent_id,
        "agentConfigId": agent_id,
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "name": doc.get("name", ""),
        "websiteUrl": doc.get("websiteUrl", ""),
        "runtimeEndpoint": doc.get("runtimeEndpoint", ""),
        "baseRuntimeEndpoint": doc.get("baseRuntimeEndpoint", ""),
        "runtimeType": doc.get("runtimeType", ""),
        "status": doc.get("status", ""),
        "trainingStatus": doc.get("trainingStatus", ""),
        "runtimeCapabilities": doc.get("runtimeCapabilities") or {},
        "tasks": doc.get("tasks") or [],
        "successCriteria": doc.get("successCriteria", ""),
        "apiSpecUrl": doc.get("apiSpecUrl", ""),
        "apiAuthConfigured": bool(doc.get("apiAuth", {}).get("headerValueConfigured")),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _tool_callable(doc: dict[str, Any]) -> dict[str, Any]:
    return AgentCallable(
        kind="tool",
        name=str(doc.get("name") or ""),
        description=str(doc.get("description") or ""),
        inputSchema=doc.get("inputSchema") or {"type": "object", "properties": {}},
        outputSchema=doc.get("outputSchema") or {"type": "object", "additionalProperties": True},
        sideEffects=str(doc.get("sideEffects") or "reads"),
        riskLevel=str(doc.get("riskLevel") or "low"),
        source=str(doc.get("source") or ""),
        connectorId=str(doc.get("connectorId") or ""),
        executionType=str(doc.get("executionType") or ""),
        permissions=doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {},
    ).model_dump()


def _skill_callable(doc: dict[str, Any]) -> dict[str, Any]:
    name = str(doc.get("toolName") or doc.get("name") or doc.get("skillId") or "skill").strip()
    if "." not in name:
        name = f"skill.{re.sub(r'[^a-zA-Z0-9_]+', '_', name).strip('_').lower()}"
    return AgentCallable(
        kind="skill",
        name=name,
        description=str(doc.get("description") or doc.get("whenToUse") or ""),
        inputSchema=doc.get("inputSchema") or {"type": "object", "properties": {"instruction": {"type": "string"}}},
        outputSchema=doc.get("outputSchema") or {"type": "object", "additionalProperties": True},
        sideEffects=str(doc.get("sideEffects") or "reads"),
        riskLevel=str(doc.get("riskLevel") or "medium"),
        source=str(doc.get("source") or "skill_registry"),
        capabilityId=str(doc.get("capabilityId") or doc.get("skillId") or ""),
        trajectoryIds=[str(item) for item in doc.get("trajectoryIds") or []],
        runtime=str(doc.get("runtime") or ""),
        permissions=doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {},
    ).model_dump()


def _agent_config_payload(agent_config: dict[str, Any], context: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    payload = AgentConfig(
        agentId=str(agent_config.get("agentId") or ""),
        name=str(agent_config.get("name") or ""),
        email=str(agent_config.get("email") or ""),
        companyId=str(agent_config.get("companyId") or ""),
        websiteUrl=str(agent_config.get("websiteUrl") or ""),
        runtimeEndpoint=str(agent_config.get("runtimeEndpoint") or ""),
        baseRuntimeEndpoint=str(agent_config.get("baseRuntimeEndpoint") or ""),
        runtimeType=str(agent_config.get("runtimeType") or "generalist_with_company_capabilities"),
        status=str(agent_config.get("status") or "draft"),
        trainingStatus=str(agent_config.get("trainingStatus") or "not_started"),
        runtimeCapabilities=agent_config.get("runtimeCapabilities") or {},
        tasks=agent_config.get("tasks") or [],
        tools=[_tool_callable(tool) for tool in context.get("tools") or []],
        skills=[_skill_callable(skill) for skill in context.get("skills") or []],
        memory=memory,
        riskPolicy={"writesRequireApproval": bool((agent_config.get("runtimeCapabilities") or {}).get("humanApprovalForWrites", True))},
        createdAt=agent_config.get("createdAt"),
        updatedAt=agent_config.get("updatedAt"),
    )
    return payload.model_dump()


async def _capability_context(agent_config: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {"agentId": agent_config.get("agentId", "")}
    company_id = str(agent_config.get("companyId") or "")
    if company_id:
        query = {"$or": [query, {"companyId": company_id}]}

    skills = await capabilities_collection.find(
        {**query, "capabilityKind": "skill"} if "$or" not in query else {"$and": [query, {"capabilityKind": "skill"}]},
        {"_id": 0},
    ).to_list(length=200)
    tools = []
    if company_id:
        tools = await tools_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
    skill_tools = [_skill_callable(skill) for skill in skills]
    return {"skills": skills, "tools": tools, "callables": [_tool_callable(tool) for tool in tools] + skill_tools}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]{4,}", value.lower()) if token}


def _match_skill(prompt: str, skills: list[dict[str, Any]]) -> dict[str, Any] | None:
    prompt_tokens = _tokens(prompt)
    if not prompt_tokens:
        return None
    best: tuple[int, dict[str, Any] | None] = (0, None)
    for skill in skills:
        text = " ".join(
            str(skill.get(key) or "")
            for key in ("name", "description", "whenToUse", "runtime", "source")
        )
        skill_tokens = _tokens(text)
        score = len(prompt_tokens & skill_tokens)
        if score > best[0]:
            best = (score, skill)
    return best[1] if best[0] >= 1 else None


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    name = str(action.get("action") or action.get("name") or "")
    args = action.get("args") if isinstance(action.get("args"), dict) else action.get("arguments")
    if not isinstance(args, dict):
        args = {}
    if name in {"navigate", "click", "input", "type", "select_dropdown", "send_keys", "wait", "done", "extract"}:
        name = f"browser.{name}"
    return {"name": name, "arguments": args, "reasoning": str(action.get("reasoning") or "")}


def _requires_human_approval(action_name: str) -> bool:
    lowered = action_name.lower()
    return any(token in lowered for token in ("send_email", "send_message", "smtp_send", "delete", "create_invoice", "payment", "transfer", ".create", ".update"))


def _is_browser_tool(tool_name: str) -> bool:
    return tool_name.startswith("browser.") or tool_name in {"navigate", "click", "input", "type", "select_dropdown", "send_keys", "wait", "done", "extract"} or tool_name == "api.human_approval"


def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    fn = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else None
    if fn:
        return {"name": str(fn.get("name") or ""), "arguments": fn.get("arguments") if isinstance(fn.get("arguments"), dict) else {}}
    return {
        "name": str(tool_call.get("name") or ""),
        "arguments": tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {},
    }


def _step_index(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("step_index") or 0)
    except (TypeError, ValueError):
        return 0


def _external_runtime_looks_mismatched(agent_config: dict[str, Any], data: dict[str, Any]) -> bool:
    agent_name = str(agent_config.get("name") or "").lower()
    if "autocinema" in agent_name:
        return False
    text = " ".join(
        str(data.get(key) or "")
        for key in ("reasoning", "content", "message")
    ).lower()
    return "autocinema" in text or "custom operator instructions" in text


async def _execute_connector_tool_calls(agent_config: dict[str, Any], data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    company_id = str(agent_config.get("companyId") or "")
    if not company_id:
        return data
    raw_calls = data.get("tool_calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        return data

    state = payload.get("state_in") if isinstance(payload.get("state_in"), dict) else {}
    approved = set(state.get("approvedConnectorToolCalls") or [])
    passthrough_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = list(data.get("tool_results") or [])
    executed_any = False

    for idx, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            passthrough_calls.append(raw_call)
            continue
        call = _normalize_tool_call(raw_call)
        name = call["name"]
        arguments = call["arguments"]
        if not name or _is_browser_tool(name):
            passthrough_calls.append(raw_call)
            continue

        if name.startswith("skill."):
            skills = await capabilities_collection.find(
                {"agentId": agent_config.get("agentId", ""), "capabilityKind": "skill"},
                {"_id": 0},
            ).to_list(length=200)
            skill = next((item for item in skills if _skill_callable(item).get("name") == name), None)
            if not skill:
                tool_results.append({"tool": name, "success": False, "error": "Skill not found"})
                executed_any = True
                continue
            skill_response = await _web_skill_response(
                agent_config,
                skill,
                str(arguments.get("instruction") or payload.get("prompt") or ""),
                payload,
            )
            passthrough_calls.extend(skill_response.get("tool_calls") or [])
            tool_results.append({"tool": name, "success": True, "output": {"content": skill_response.get("content"), "capabilityMatch": skill_response.get("capability_match")}})
            executed_any = True
            continue

        approval_key = f"{name}:{idx}:{hash(str(arguments))}"
        if _requires_human_approval(name) and approval_key not in approved:
            return {
                **data,
                "tool_calls": [
                    {
                        "name": "api.human_approval",
                        "arguments": {
                            "title": f"Approve {name}",
                            "message": "This connector tool can write or send data. Confirm before Automata executes it.",
                            "proposedAction": {"name": name, "arguments": arguments},
                            "approvalKey": approval_key,
                        },
                    }
                ],
                "tool_results": tool_results,
                "done": False,
                "state_out": {
                    **(data.get("state_out") if isinstance(data.get("state_out"), dict) else {}),
                    "pendingConnectorApproval": approval_key,
                    "pendingConnectorToolCall": {"name": name, "arguments": arguments},
                    "approvedConnectorToolCalls": list(approved),
                },
            }

        try:
            result = await execute_connector_tool(company_id=company_id, tool_name=name, arguments=arguments)
            tool_results.append(result)
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="ok" if result.get("success") else "failed",
                payload={"arguments": arguments},
                result=result,
            )
            executed_any = True
        except ConnectorExecutionError as exc:
            tool_results.append({"tool": name, "success": False, "error": str(exc)})
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="failed",
                payload={"arguments": arguments},
                error=str(exc),
            )
            executed_any = True

    if not executed_any:
        return data

    return {
        **data,
        "tool_calls": passthrough_calls,
        "tool_results": tool_results,
        "content": data.get("content") or "Connector tools executed.",
        "done": bool(data.get("done")) and not passthrough_calls,
    }


async def _load_skill_trajectory(skill: dict[str, Any]) -> dict[str, Any] | None:
    trajectory_ids = [str(item) for item in skill.get("trajectoryIds") or [] if item]
    if not trajectory_ids:
        return None
    query = {"trajectoryId": {"$in": trajectory_ids}}
    preferred = await trajectories_collection.find_one({**query, "status": {"$in": ["approved", "harvested"]}}, {"_id": 0})
    if preferred:
        return preferred
    return await trajectories_collection.find_one(query, {"_id": 0})


async def _web_skill_response(agent_config: dict[str, Any], skill: dict[str, Any], prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("state_in") if isinstance(payload.get("state_in"), dict) else {}
    skill_id = str(skill.get("capabilityId") or skill.get("skillId") or skill.get("name") or "")

    trajectory = await _load_skill_trajectory(skill)
    raw_actions = []
    if trajectory:
        raw_actions = trajectory.get("trajectory") or trajectory.get("actions") or trajectory.get("steps") or []
    actions = [_normalize_action(action) for action in raw_actions if isinstance(action, dict)]
    actions = [action for action in actions if action["name"]]

    if actions and str(trajectory.get("status") if trajectory else "") in {"approved", "harvested"}:
        progress = state.get("automata_trajectory_progress") if isinstance(state.get("automata_trajectory_progress"), dict) else {}
        trajectory_id = str(trajectory.get("trajectoryId") or "")
        current = progress.get(trajectory_id) if isinstance(progress.get(trajectory_id), dict) else {}
        index = int(current.get("index") or 0)
        approval_pending = bool(current.get("approvalPending"))
        approved_actions = set(current.get("approvedActions") or [])

        if index >= len(actions):
            return {
                "protocol_version": "1.0",
                "tool_calls": [],
                "content": f"Completed harvested skill '{skill.get('name', 'skill')}'.",
                "reasoning": "All harvested trajectory tools have been replayed.",
                "done": True,
                "state_out": state,
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        action = actions[index]
        action_key = f"{trajectory_id}:{index}"
        if action["name"] == "api.human_approval":
            approval_args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            body = str(approval_args.get("body") or approval_args.get("message") or approval_args.get("summary") or "")
            next_progress = {
                **progress,
                trajectory_id: {"index": index + 1, "approvalPending": True, "approvedActions": list(approved_actions)},
            }
            return {
                "protocol_version": "1.0",
                "tool_calls": [],
                "content": body or f"Skill '{skill.get('name', 'skill')}' prepared an action that needs human approval.",
                "reasoning": action["reasoning"] or "Human approval is required before executing the proposed write/send action.",
                "done": True,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }
        if _requires_human_approval(action["name"]) and action_key not in approved_actions and not approval_pending:
            next_progress = {
                **progress,
                trajectory_id: {"index": index, "approvalPending": True, "approvedActions": list(approved_actions)},
            }
            return {
                "protocol_version": "1.0",
                "tool_calls": [
                    {
                        "name": "api.human_approval",
                        "arguments": {
                            "title": f"Approve {action['name']}",
                            "message": "This harvested trajectory is about to perform a write/send action. Confirm before continuing.",
                            "proposedAction": action,
                        },
                    }
                ],
                "content": None,
                "reasoning": f"Matched harvested skill '{skill.get('name', 'skill')}'. Human approval is required before executing {action['name']}.",
                "done": False,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        if approval_pending and action_key not in approved_actions:
            next_progress = {
                **progress,
                trajectory_id: {"index": index, "approvalPending": True, "approvedActions": list(approved_actions)},
            }
            return {
                "protocol_version": "1.0",
                "tool_calls": [],
                "content": f"Matched skill '{skill.get('name', 'skill')}' is waiting for human approval before executing {action['name']}.",
                "reasoning": "Human approval is required before this write/send action can continue.",
                "done": True,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        next_index = index + 1
        next_progress = {
            **progress,
            trajectory_id: {"index": next_index, "approvalPending": approval_pending, "approvedActions": list(approved_actions)},
        }
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": action["name"], "arguments": action["arguments"]}],
            "content": None,
            "reasoning": action["reasoning"] or f"Replaying harvested skill '{skill.get('name', 'skill')}' step {next_index}/{len(actions)}.",
            "done": next_index >= len(actions),
            "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
            "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
        }

    if state.get("matchedSkillId") == skill_id:
        return {
            "protocol_version": "1.0",
            "tool_calls": [],
            "content": f"Matched skill '{skill.get('name', 'skill')}', but it has no approved executable trajectory yet. Harvest and approve this skill before autonomous replay.",
            "reasoning": "Capability matched; stopped instead of falling back to an unrelated external runtime policy.",
            "done": True,
            "state_out": state,
            "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", "")},
        }

    url = str(payload.get("url") or agent_config.get("websiteUrl") or "").strip()
    if url:
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": "browser.navigate", "arguments": {"url": url}}],
            "content": None,
            "reasoning": f"Matched skill '{skill.get('name', 'skill')}'. Navigating to the configured runtime surface before planning the skill steps.",
            "done": False,
            "state_out": {**state, "matchedSkillId": skill_id},
            "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", "")},
        }
    return {
        "protocol_version": "1.0",
        "tool_calls": [],
        "content": f"Matched skill '{skill.get('name', 'skill')}'. The trajectory is available as a draft and requires harvested executable steps before autonomous replay.",
        "reasoning": "Capability matched, but no executable trajectory steps are approved yet.",
        "done": True,
        "state_out": state,
        "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", "")},
    }


async def agent_step_result(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent_config = await load_agent_config(agent_id)
    prompt = str(payload.get("prompt") or payload.get("task") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="task or prompt is required")

    payload = dict(payload)
    payload["prompt"] = prompt
    payload["task"] = prompt

    context = await _capability_context(agent_config)
    state_in = payload.get("state_in") if isinstance(payload.get("state_in"), dict) else {}
    memory = state_in.get("memory") if isinstance(state_in.get("memory"), dict) else {}
    payload["agentConfig"] = _agent_config_payload(agent_config, context, memory)
    payload["context"] = {
        **(payload.get("context") if isinstance(payload.get("context"), dict) else {}),
        "automataCapabilities": context,
        "agentConfig": payload["agentConfig"],
    }
    await record_runtime_event(
        agent_id=agent_id,
        company_id=str(agent_config.get("companyId") or ""),
        event_type="agent.step.request",
        step_index=int(payload.get("step_index") or 0),
        payload={"prompt": prompt, "url": payload.get("url"), "agentConfig": payload["agentConfig"]},
    )

    matched_skill = _match_skill(prompt, context["skills"])
    matched_skill_id = str((matched_skill or {}).get("capabilityId") or (matched_skill or {}).get("skillId") or (matched_skill or {}).get("name") or "")
    if matched_skill and (_step_index(payload) == 0 or state_in.get("matchedSkillId") == matched_skill_id):
        data = await _web_skill_response(agent_config, matched_skill, prompt, payload)
    else:
        endpoint = step_url(str(agent_config.get("baseRuntimeEndpoint") or DEFAULT_BASE_RUNTIME_ENDPOINT))
        if not endpoint:
            raise HTTPException(status_code=409, detail="Agent runtime is not deployed yet")
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(endpoint, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Agent runtime request failed: {exc}") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"runtimeStatus": response.status_code, "body": response.text})
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}
        if matched_skill and isinstance(data, dict) and _external_runtime_looks_mismatched(agent_config, data):
            data = await _web_skill_response(agent_config, matched_skill, prompt, payload)

    if isinstance(data, dict):
        data = await _execute_connector_tool_calls(agent_config, data, payload)
        state_out = data.get("state_out") if isinstance(data.get("state_out"), dict) else {}
        data["state_out"] = {**state_out, "memory": {**memory, **(state_out.get("memory") if isinstance(state_out.get("memory"), dict) else {})}}
        data.setdefault(
            "executionMode",
            "skill_replay" if data.get("capability_match") else "connector_tool" if data.get("tool_results") else "generalist",
        )

    await record_runtime_event(
        agent_id=agent_id,
        company_id=str(agent_config.get("companyId") or ""),
        event_type="agent.step.result",
        step_index=int(payload.get("step_index") or 0),
        status="ok",
        result=data if isinstance(data, dict) else {"raw": data},
    )

    return data


async def agent_step(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent_config = await load_agent_config(agent_id)
    data = await agent_step_result(agent_id, payload)
    return {
        "agentId": agent_id,
        "agentConfigId": agent_id,
        "agentName": agent_config.get("name", ""),
        "runtimeEndpoint": agent_config.get("runtimeEndpoint", ""),
        "baseRuntimeEndpoint": agent_config.get("baseRuntimeEndpoint", ""),
        "result": data,
    }
