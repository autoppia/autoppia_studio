from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.assistant.context import AssistantContext
from app.assistant.prompts import system_prompt
from app.assistant.schemas import AssistantMode
from app.assistant.tools import AutomataAssistantTools
from app.database import assistant_conversations_collection
from app.routes.onboarding import _default_draft, _run_onboarding_agent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message(role: str, content: str, *, kind: str = "message", tool_name: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "role": role,
        "type": kind,
        "content": content,
        "toolName": tool_name,
        "status": "completed",
        "createdAt": now_iso(),
        "metadata": metadata or {},
    }


def conversation_payload(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversationId": doc.get("conversationId", ""),
        "email": doc.get("email", ""),
        "mode": doc.get("mode", "studio_global"),
        "companyId": doc.get("companyId", ""),
        "route": doc.get("route", ""),
        "messages": doc.get("messages", []),
        "draft": doc.get("draft"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


class AutomataAssistantService:
    def __init__(self, context: AssistantContext):
        self.context = context
        self.tools = AutomataAssistantTools(context)

    async def create_conversation(self, seed_prompt: str = "") -> dict[str, Any]:
        now = now_iso()
        messages = [
            _message(
                "assistant",
                "Hey. I am Automata. I can help you configure Studio, create agents, review connectors, and understand what needs attention.",
            )
        ]
        draft = _default_draft() if self.context.mode == "onboarding" else None
        if seed_prompt.strip():
            messages.append(_message("user", seed_prompt.strip()))
            reply, events, draft = await self.respond(seed_prompt.strip(), existing_draft=draft)
            messages.extend(events)
            messages.append(_message("assistant", reply))
        doc = {
            "conversationId": str(uuid.uuid4()),
            "email": self.context.email,
            "mode": self.context.mode,
            "companyId": self.context.company_id,
            "route": self.context.route,
            "systemPrompt": system_prompt(self.context.mode),
            "messages": messages,
            "draft": draft,
            "createdAt": now,
            "updatedAt": now,
        }
        await assistant_conversations_collection.insert_one(doc)
        return conversation_payload(doc)

    async def load_owned_conversation(self, conversation_id: str) -> dict[str, Any]:
        doc = await assistant_conversations_collection.find_one({"conversationId": conversation_id, "email": self.context.email}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Assistant conversation not found")
        if self.context.company_id and doc.get("companyId") and doc.get("companyId") != self.context.company_id:
            raise HTTPException(status_code=404, detail="Assistant conversation not found")
        return doc

    async def send_message(self, conversation_id: str, message: str) -> dict[str, Any]:
        doc = await self.load_owned_conversation(conversation_id)
        effective_company_id = self.context.company_id or str(doc.get("companyId") or "")
        if effective_company_id and effective_company_id != self.context.company_id:
            effective_context = AssistantContext(
                email=self.context.email,
                mode=self.context.mode,
                company_id=effective_company_id,
                route=self.context.route,
                visible_state=self.context.visible_state,
                allowed_scopes=self.context.allowed_scopes,
            )
            self.context = effective_context
            self.tools = AutomataAssistantTools(effective_context)
        stored_mode = doc.get("mode", "studio_global")
        current_mode = stored_mode if self.context.mode == "studio_global" and stored_mode != "studio_global" else self.context.mode
        draft = doc.get("draft")
        messages = list(doc.get("messages") or [])
        messages.append(_message("user", message.strip()))
        reply, events, draft = await self.respond(message, existing_draft=draft, mode=current_mode)
        messages.extend(events)
        messages.append(_message("assistant", reply))
        update = {
            "messages": messages,
            "draft": draft,
            "mode": current_mode,
            "route": self.context.route or doc.get("route", ""),
            "companyId": self.context.company_id or doc.get("companyId", ""),
            "updatedAt": now_iso(),
        }
        await assistant_conversations_collection.update_one(
            {"conversationId": conversation_id, "email": self.context.email},
            {"$set": update},
        )
        return conversation_payload({**doc, **update})

    async def respond(
        self,
        user_message: str,
        *,
        existing_draft: dict[str, Any] | None = None,
        mode: AssistantMode | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        active_mode = mode or self.context.mode
        if active_mode == "onboarding":
            draft = existing_draft or _default_draft()
            draft, onboarding_events = await _run_onboarding_agent(draft, user_message)
            reply = next(
                (event.get("content", "") for event in reversed(onboarding_events) if event.get("type") == "assistant_summary"),
                "I updated the onboarding draft.",
            )
            return reply, onboarding_events, draft

        events: list[dict[str, Any]] = [_message("assistant", "Checking your Studio workspace.", kind="thinking")]
        lower = user_message.lower()
        if any(token in lower for token in ("connector", "credential", "integration", "conector", "credencial")) or active_mode == "connectors":
            connectors = await self.tools.list_connectors()
            events.append(_message("tool", f"Found {len(connectors)} connector(s).", kind="tool_result", tool_name="studio.list_connectors", metadata={"connectors": connectors}))
            return self._connectors_reply(connectors), events, existing_draft
        if any(token in lower for token in ("skill", "tool", "capabilit", "trajectory", "harvest", "habilidad")) or active_mode == "capabilities":
            capabilities = await self.tools.list_capabilities()
            events.append(_message("tool", "Loaded scoped tools and skills.", kind="tool_result", tool_name="studio.list_capabilities", metadata=capabilities))
            return self._capabilities_reply(capabilities), events, existing_draft
        if any(token in lower for token in ("agent", "runtime", "step")) or active_mode == "agent_detail":
            agents = await self.tools.list_agents()
            events.append(_message("tool", f"Found {len(agents)} agent config(s).", kind="tool_result", tool_name="studio.list_agents", metadata={"agents": agents}))
            return self._agents_reply(agents), events, existing_draft
        if any(token in lower for token in ("work", "task", "pending", "approval", "tarea")) or active_mode == "work":
            work_items = await self.tools.list_work_items()
            events.append(_message("tool", f"Found {len(work_items)} work item(s).", kind="tool_result", tool_name="studio.list_work_items", metadata={"workItems": work_items}))
            return self._work_reply(work_items), events, existing_draft

        snapshot = await self.tools.studio_snapshot()
        events.append(_message("tool", "Loaded your scoped Studio snapshot.", kind="tool_result", tool_name="studio.snapshot", metadata=snapshot))
        return self._snapshot_reply(snapshot), events, existing_draft

    def _snapshot_reply(self, snapshot: dict[str, Any]) -> str:
        counts = snapshot.get("counts", {})
        if not counts.get("companies"):
            return "You do not have a company configured yet. I can help you start onboarding and create the company, connectors, tasks, and first agent."
        return (
            f"I can see {counts.get('companies', 0)} company, {counts.get('agents', 0)} agent config(s), "
            f"{counts.get('connectors', 0)} connector(s), {counts.get('tools', 0)} tool(s), "
            f"and {counts.get('skills', 0)} skill(s) in your scoped Studio workspace. "
            "Tell me what you want to inspect or configure next."
        )

    def _connectors_reply(self, connectors: list[dict[str, Any]]) -> str:
        if not connectors:
            return "I do not see connectors for this company yet. In onboarding we should add each external system, then configure credentials in the connector settings."
        needs_auth = [item.get("name") for item in connectors if item.get("status") in {"needs_auth", "not_connected"}]
        if needs_auth:
            return f"These connectors need attention: {', '.join(str(name) for name in needs_auth[:6])}. I can help you decide which credentials or docs each one needs."
        return "Your connectors are present and none are marked as needing auth. I can help review which tools or skills should be generated from them."

    def _capabilities_reply(self, capabilities: dict[str, Any]) -> str:
        tools = capabilities.get("tools") or []
        skills = capabilities.get("skills") or []
        return f"This company has {len(tools)} tool(s) and {len(skills)} skill(s) visible to you. I can help explain what is callable at runtime and what still needs harvesting or judging."

    def _agents_reply(self, agents: list[dict[str, Any]]) -> str:
        if not agents:
            return "I do not see an AgentConfig in this scope yet. Onboarding can create the first one from company systems and benchmark tasks."
        names = ", ".join(str(agent.get("name") or agent.get("agentId")) for agent in agents[:5])
        return f"I found these AgentConfigs: {names}. I can help inspect runtime settings, tasks, evals, tools, skills, and knowledge wiring."

    def _work_reply(self, work_items: list[dict[str, Any]]) -> str:
        pending = [item for item in work_items if item.get("status") not in {"done", "completed", "cancelled"}]
        return f"I found {len(work_items)} work item(s), with {len(pending)} still active or pending in your scope."
