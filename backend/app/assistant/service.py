from __future__ import annotations

import json
import os
import re
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

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - local installs may omit the optional SDK.
    AsyncOpenAI = None  # type: ignore[assignment]

ASSISTANT_MODEL = os.getenv("AUTOMATA_ASSISTANT_MODEL", "gpt-5-mini")
ASSISTANT_REASONING_EFFORT = os.getenv("AUTOMATA_ASSISTANT_REASONING_EFFORT", "minimal")
ASSISTANT_TEXT_VERBOSITY = os.getenv("AUTOMATA_ASSISTANT_TEXT_VERBOSITY", "low")
ASSISTANT_MAX_OUTPUT_TOKENS = int(os.getenv("AUTOMATA_ASSISTANT_MAX_OUTPUT_TOKENS", "700"))
MAX_TOOL_ROUNDS = 4


ASSISTANT_FUNCTION_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "studio_snapshot",
        "description": "Load a scoped summary of the user's Automata Studio workspace, including companies, counts, agents, connectors, tools, skills, knowledge documents, benchmark tasks, and work items.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_companies",
        "description": "List companies owned by the authenticated user and identify the active company when company scope is present. Use this to answer questions about company names or active company context.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_connectors",
        "description": "List connectors for the scoped company, with secrets masked. Use for integration, credential, connector status, or auth questions.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_capabilities",
        "description": "List callable tools and approved or draft skills for the scoped company. Use for tools, skills, trajectories, harvesting, judging, and runtime callable questions.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_agents",
        "description": "List AgentConfigs for the scoped company. Use for questions about agents, runtime config, /step execution, tasks, or deployment.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_work_items",
        "description": "List work items for the scoped company. Use for scheduled work, pending jobs, approvals, active work, retries, and ownership.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_entities",
        "description": "List semantic entity models for the scoped company. Use for questions about company data models, relationships, and entity grounding.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_generate_entities_from_openapi",
        "description": "Preview or create semantic entity models for the scoped company from an OpenAPI JSON or Swagger docs URL. Use apply=true only when the user explicitly asks to create/generate/add entities.",
        "parameters": {
            "type": "object",
            "properties": {
                "sourceUrl": {"type": "string"},
                "apply": {"type": "boolean"},
                "replaceExisting": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["sourceUrl"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_list_approvals",
        "description": "List approval requests for the scoped company. Use for pending approval or write confirmation questions.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_knowledge_documents",
        "description": "List knowledge documents for the scoped company. Use for questions about uploaded docs, indexed knowledge, or grounding sources.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_artifacts",
        "description": "List created artifacts for the scoped company. Use for questions about documents, HTML/React/SVG artifacts, diagrams, exports, or generated files.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
]


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


def conversation_summary(doc: dict[str, Any]) -> dict[str, Any]:
    messages = [item for item in doc.get("messages", []) if isinstance(item, dict)]
    title = ""
    for message in reversed(messages):
        if message.get("role") == "user" and str(message.get("content") or "").strip():
            title = str(message.get("content") or "").strip()
            break
    if not title:
        for message in messages:
            if str(message.get("content") or "").strip():
                title = str(message.get("content") or "").strip()
                break
    last_message = next((item for item in reversed(messages) if str(item.get("content") or "").strip()), {})
    return {
        "conversationId": doc.get("conversationId", ""),
        "email": doc.get("email", ""),
        "mode": doc.get("mode", "studio_global"),
        "companyId": doc.get("companyId", ""),
        "route": doc.get("route", ""),
        "title": title[:100] or "New conversation",
        "lastMessage": str(last_message.get("content") or "")[:180],
        "messageCount": len(messages),
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
            reply, events, draft = await self.respond(seed_prompt.strip(), existing_draft=draft, history=messages)
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

    async def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return conversation_payload(await self.load_owned_conversation(conversation_id))

    async def list_conversations(self, *, limit: int = 30) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"email": self.context.email}
        if self.context.company_id:
            query["companyId"] = self.context.company_id
        cursor = assistant_conversations_collection.find(query, {"_id": 0}).sort("updatedAt", -1).limit(max(1, min(limit, 100)))
        docs = await cursor.to_list(length=max(1, min(limit, 100)))
        return [conversation_summary(doc) for doc in docs]

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
        reply, events, draft = await self.respond(message, existing_draft=draft, mode=current_mode, history=messages)
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
        history: list[dict[str, Any]] | None = None,
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

        quick = await self._respond_with_quick_path(user_message, existing_draft=existing_draft)
        if quick:
            return quick

        if os.getenv("OPENAI_API_KEY"):
            try:
                return await self._respond_with_llm(user_message, active_mode=active_mode, existing_draft=existing_draft, history=history or [])
            except Exception:
                # The Studio assistant should degrade gracefully in local/dev environments.
                pass

        return await self._respond_with_rules(user_message, active_mode=active_mode, existing_draft=existing_draft)

    async def _respond_with_rules(
        self,
        user_message: str,
        *,
        active_mode: AssistantMode,
        existing_draft: dict[str, Any] | None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
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
        if "entit" in lower or "entities" in lower or "entidad" in lower:
            url = self._extract_url(user_message)
            if url and ("openapi" in lower or "/docs" in lower or "swagger" in lower):
                apply = any(token in lower for token in ("create", "generate", "add", "crear", "genera", "añad", "anad"))
                replace_existing = any(token in lower for token in ("replace", "overwrite", "reimport", "re-import", "reemplaz", "sobrescrib"))
                result = await self.tools.generate_entities_from_openapi(source_url=url, apply=apply, replace_existing=replace_existing, limit=25)
                events.append(
                    _message(
                        "tool",
                        self._entity_generation_summary(result),
                        kind="tool_result",
                        tool_name="studio_generate_entities_from_openapi",
                        metadata=result,
                    )
                )
                return self._entity_generation_reply(result), events, existing_draft
            entities = await self.tools.list_entities()
            events.append(_message("tool", f"Loaded {len(entities)} entities.", kind="tool_result", tool_name="studio_list_entities", metadata={"entities": entities}))
            return self._entities_reply(entities), events, existing_draft
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

    async def _respond_with_llm(
        self,
        user_message: str,
        *,
        active_mode: AssistantMode,
        existing_draft: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if AsyncOpenAI is None:
            raise RuntimeError("OpenAI SDK is not installed")
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        events: list[dict[str, Any]] = [_message("assistant", "Thinking with Studio tools.", kind="thinking")]
        input_items = self._llm_input(history, user_message)
        instructions = self._llm_instructions(active_mode)

        response = await client.responses.create(
            **self._llm_request(instructions=instructions, input_items=input_items)
        )
        for _ in range(MAX_TOOL_ROUNDS):
            calls = self._function_calls(response)
            if not calls:
                break
            tool_outputs = []
            for call in calls:
                output = await self._execute_llm_tool(call["name"], call["arguments"])
                events.append(
                    _message(
                        "tool",
                        self._tool_event_summary(call["name"], output),
                        kind="tool_result",
                        tool_name=call["name"],
                        metadata=output,
                    )
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(output, ensure_ascii=False, default=str)[:20000],
                    }
                )
            previous_response_id = str(getattr(response, "id", "") or "")
            request = self._llm_request(
                instructions=instructions,
                input_items=tool_outputs if previous_response_id else [*input_items, *tool_outputs],
            )
            if previous_response_id:
                request["previous_response_id"] = previous_response_id
            response = await client.responses.create(**request)

        text = str(getattr(response, "output_text", "") or "").strip()
        if not text:
            snapshot = await self.tools.studio_snapshot()
            events.append(_message("tool", "Loaded your scoped Studio snapshot.", kind="tool_result", tool_name="studio_snapshot", metadata=snapshot))
            text = self._snapshot_reply(snapshot)
        return text, events, existing_draft

    async def _respond_with_quick_path(
        self,
        user_message: str,
        *,
        existing_draft: dict[str, Any] | None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None] | None:
        lower = " ".join(user_message.lower().strip().split())
        if lower in {"hi", "hello", "hey", "hola", "buenas"}:
            return "Hello. What do you want to inspect or configure in Studio?", [], existing_draft
        company_terms = ("company name", "current company name", "active company name", "which company", "what company", "nombre de la company", "empresa actual")
        if not any(term in lower for term in company_terms):
            return None
        companies = await self.tools.list_companies(limit=20)
        active_company = next((company for company in companies if company.get("companyId") == self.context.company_id), None)
        if not active_company:
            return None
        events = [
            _message("assistant", "Checking company context.", kind="thinking"),
            _message(
                "tool",
                f"Loaded {len(companies)} companies.",
                kind="tool_result",
                tool_name="studio_list_companies",
                metadata={"companies": companies, "activeCompanyId": self.context.company_id, "activeCompany": active_company},
            ),
        ]
        others = [str(company.get("name") or company.get("companyId")) for company in companies if company.get("companyId") != self.context.company_id]
        suffix = f" You also own: {', '.join(others)}." if others else ""
        return f'Your active company is "{active_company.get("name") or active_company.get("companyId")}".{suffix}', events, existing_draft

    def _llm_request(self, *, instructions: str, input_items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": os.getenv("AUTOMATA_ASSISTANT_MODEL", ASSISTANT_MODEL),
            "instructions": instructions,
            "input": input_items,
            "tools": ASSISTANT_FUNCTION_TOOLS,
            "reasoning": {"effort": os.getenv("AUTOMATA_ASSISTANT_REASONING_EFFORT", ASSISTANT_REASONING_EFFORT)},
            "text": {"verbosity": os.getenv("AUTOMATA_ASSISTANT_TEXT_VERBOSITY", ASSISTANT_TEXT_VERBOSITY)},
            "max_output_tokens": int(os.getenv("AUTOMATA_ASSISTANT_MAX_OUTPUT_TOKENS", str(ASSISTANT_MAX_OUTPUT_TOKENS))),
        }

    def _llm_instructions(self, mode: AssistantMode) -> str:
        return "\n\n".join(
            [
                system_prompt(mode),
                "You are a real tool-using agent. Use function tools whenever the answer depends on current Studio data.",
                "Answer directly and concisely. If the user asks for names or counts, call the relevant list/snapshot tool and cite the concrete data you found.",
                "If the user explicitly asks to create, generate, add, or import entities from OpenAPI/docs, call studio_generate_entities_from_openapi with apply=true. If they only ask what would be generated, call it with apply=false.",
                "Do not invent resources. If a tool returns an empty list, say that clearly and suggest the next useful action.",
                "Never reveal raw secrets. Tool outputs already mask secret-like fields; keep them masked.",
            ]
        )

    def _llm_input(self, history: list[dict[str, Any]], user_message: str) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for message in history[-12:]:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            if role not in {"user", "assistant"}:
                continue
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            items.append({"role": role, "content": content})
        if not items or items[-1].get("role") != "user" or items[-1].get("content") != user_message.strip():
            items.append({"role": "user", "content": user_message.strip()})
        return items

    def _response_items(self, response: Any) -> list[dict[str, Any]]:
        items = []
        for item in getattr(response, "output", []) or []:
            if hasattr(item, "model_dump"):
                items.append(item.model_dump())
            elif isinstance(item, dict):
                items.append(item)
        return items

    def _function_calls(self, response: Any) -> list[dict[str, Any]]:
        calls = []
        for item in self._response_items(response):
            if item.get("type") != "function_call":
                continue
            raw_args = item.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                arguments = {}
            calls.append(
                {
                    "call_id": str(item.get("call_id") or item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "arguments": arguments,
                }
            )
        return [call for call in calls if call["call_id"] and call["name"]]

    async def _execute_llm_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        limit = int(arguments.get("limit") or 20) if isinstance(arguments, dict) else 20
        if name == "studio_snapshot":
            return await self.tools.studio_snapshot()
        if name == "studio_list_companies":
            companies = await self.tools.list_companies(limit=min(limit, 20))
            active_company = next((company for company in companies if company.get("companyId") == self.context.company_id), None)
            return {"companies": companies, "activeCompanyId": self.context.company_id, "activeCompany": active_company}
        if name == "studio_list_connectors":
            return {"connectors": await self.tools.list_connectors(limit=min(limit, 50))}
        if name == "studio_list_capabilities":
            return await self.tools.list_capabilities(limit=min(limit, 50))
        if name == "studio_list_agents":
            return {"agents": await self.tools.list_agents(limit=min(limit, 30))}
        if name == "studio_list_work_items":
            return {"workItems": await self.tools.list_work_items(limit=min(limit, 50))}
        if name == "studio_list_entities":
            return {"entities": await self.tools.list_entities(limit=min(limit, 100))}
        if name == "studio_generate_entities_from_openapi":
            source_url = str(arguments.get("sourceUrl") or arguments.get("source_url") or "").strip()
            if not source_url:
                return {"error": "sourceUrl is required"}
            return await self.tools.generate_entities_from_openapi(
                source_url=source_url,
                apply=bool(arguments.get("apply")),
                replace_existing=bool(arguments.get("replaceExisting")),
                limit=min(limit, 100),
            )
        if name == "studio_list_approvals":
            return {"approvals": await self.tools.list_approvals(limit=min(limit, 50))}
        if name == "studio_list_knowledge_documents":
            return {"documents": await self.tools.list_knowledge_documents(limit=min(limit, 50))}
        if name == "studio_list_artifacts":
            return {"artifacts": await self.tools.list_artifacts(limit=min(limit, 50))}
        return {"error": f"Unknown Studio tool: {name}"}

    def _tool_event_summary(self, name: str, output: dict[str, Any]) -> str:
        if name == "studio_snapshot":
            counts = output.get("counts") if isinstance(output.get("counts"), dict) else {}
            return f"Loaded workspace snapshot: {counts.get('companies', 0)} companies, {counts.get('connectors', 0)} connectors, {counts.get('tools', 0)} tools, {counts.get('skills', 0)} skills."
        key = next((item for item in ("companies", "connectors", "agents", "workItems", "entities", "approvals", "documents", "artifacts") if isinstance(output.get(item), list)), "")
        if key:
            return f"Loaded {len(output.get(key) or [])} {key}."
        if name == "studio_generate_entities_from_openapi":
            return self._entity_generation_summary(output)
        if "tools" in output or "skills" in output:
            return f"Loaded {len(output.get('tools') or [])} tools and {len(output.get('skills') or [])} skills."
        return f"Ran {name}."

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

    def _entities_reply(self, entities: list[dict[str, Any]]) -> str:
        if not entities:
            return "This company has no semantic entities yet. I can generate a draft from an OpenAPI or Swagger docs URL, then you can review the fields and relationships."
        names = ", ".join(str(entity.get("name") or entity.get("entityId")) for entity in entities[:12])
        return f"This company has {len(entities)} semantic entit{'y' if len(entities) == 1 else 'ies'}: {names}."

    def _entity_generation_summary(self, result: dict[str, Any]) -> str:
        entities = result.get("entities") if isinstance(result.get("entities"), list) else []
        skipped = result.get("skipped") if isinstance(result.get("skipped"), list) else []
        verb = "Created" if result.get("applied") else "Proposed"
        suffix = f", skipped {len(skipped)} existing" if skipped else ""
        return f"{verb} {len(entities)} entities from OpenAPI{suffix}."

    def _entity_generation_reply(self, result: dict[str, Any]) -> str:
        entities = result.get("entities") if isinstance(result.get("entities"), list) else []
        names = ", ".join(str(entity.get("name") or "") for entity in entities[:12] if entity.get("name"))
        action = "created" if result.get("applied") else "proposed"
        if not entities:
            return f"I could not find entity-like schemas in that OpenAPI document. No entities were {action}."
        skipped = result.get("skipped") if isinstance(result.get("skipped"), list) else []
        skipped_text = f" I skipped {len(skipped)} existing entities." if skipped else ""
        return f"I {action} {len(entities)} entities from the OpenAPI document: {names}.{skipped_text}"

    def _extract_url(self, value: str) -> str:
        match = re.search(r"https?://[^\s\"'<>]+", value)
        return match.group(0).rstrip(".,)") if match else ""

    def _agents_reply(self, agents: list[dict[str, Any]]) -> str:
        if not agents:
            return "I do not see an AgentConfig in this scope yet. Onboarding can create the first one from company systems and benchmark tasks."
        names = ", ".join(str(agent.get("name") or agent.get("agentId")) for agent in agents[:5])
        return f"I found these AgentConfigs: {names}. I can help inspect runtime settings, tasks, evals, tools, skills, and knowledge wiring."

    def _work_reply(self, work_items: list[dict[str, Any]]) -> str:
        pending = [item for item in work_items if item.get("status") not in {"done", "completed", "cancelled"}]
        return f"I found {len(work_items)} work item(s), with {len(pending)} still active or pending in your scope."
