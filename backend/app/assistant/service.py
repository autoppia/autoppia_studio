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
from app.database import assistant_conversations_collection, companies_collection
from app.routes.onboarding import _default_draft, _run_onboarding_agent

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - local installs may omit the optional SDK.
    AsyncOpenAI = None  # type: ignore[assignment]

ASSISTANT_MODEL = os.getenv("AUTOMATA_ASSISTANT_MODEL", "gpt-5-mini")
ASSISTANT_ALLOWED_MODELS = ("gpt-5-mini", "gpt-5.4")
ASSISTANT_REASONING_EFFORT = os.getenv("AUTOMATA_ASSISTANT_REASONING_EFFORT", "minimal")
ASSISTANT_TEXT_VERBOSITY = os.getenv("AUTOMATA_ASSISTANT_TEXT_VERBOSITY", "low")
ASSISTANT_MAX_OUTPUT_TOKENS = int(os.getenv("AUTOMATA_ASSISTANT_MAX_OUTPUT_TOKENS", "700"))
MAX_TOOL_ROUNDS = 4


def _coverage_gap_label(eval_coverage: dict[str, Any]) -> str:
    missing: list[str] = []
    singular = {"connectors": "connector", "entities": "entity", "skills": "skill"}
    for kind in ("connectors", "entities", "skills"):
        coverage = eval_coverage.get(kind) if isinstance(eval_coverage.get(kind), dict) else {}
        try:
            total = int(coverage.get("total") or 0)
            covered = int(coverage.get("covered") or 0)
        except (TypeError, ValueError):
            continue
        count = max(0, total - covered)
        if count:
            missing.append(f"{count} {singular.get(kind, kind) if count == 1 else kind}")
    return ", ".join(missing)


def normalize_assistant_model(model: str) -> str:
    clean = (model or "").strip().lower().replace("_", "-")
    aliases = {
        "gpt5-mini": "gpt-5-mini",
        "gpt-5 mini": "gpt-5-mini",
        "gpt5 mini": "gpt-5-mini",
    }
    clean = aliases.get(clean, clean)
    if clean not in ASSISTANT_ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"model must be one of {', '.join(ASSISTANT_ALLOWED_MODELS)}")
    return clean


def default_assistant_model() -> str:
    configured = os.getenv("AUTOMATA_ASSISTANT_MODEL", ASSISTANT_MODEL)
    try:
        return normalize_assistant_model(configured)
    except HTTPException:
        return ASSISTANT_MODEL


ASSISTANT_FUNCTION_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "studio_snapshot",
        "description": "Load the scoped Studio operating state: companies, active company id, counts, setup readiness, capability factory coverage, runtime/work health, risks, and recommended next actions. Use for broad status, readiness, roadmap, next-step, or operational cockpit questions.",
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
        "name": "studio_create_work_item",
        "description": "Create a scoped Studio work item, including scheduled work. Use when the user explicitly asks to create, schedule, or set up work and has provided enough details. Do not ask for another confirmation after the user has already said yes, confirm, create, or equivalent.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "prompt": {"type": "string"},
                "successCriteria": {"type": "string"},
                "agentId": {"type": "string"},
                "agentName": {"type": "string"},
                "runTarget": {"type": "string", "enum": ["selected", "all"]},
                "browserEnabled": {"type": "boolean"},
                "browserMode": {"type": "string", "enum": ["visible", "headless"]},
                "maxCreditsPerRun": {"type": "number", "minimum": 0},
                "maxBudgetCredits": {"type": "number", "minimum": 0},
                "maxSteps": {"type": "integer", "minimum": 1, "maximum": 30},
                "triggerType": {"type": "string", "enum": ["manual", "scheduled"]},
                "scheduleFrequency": {"type": "string", "enum": ["none", "daily", "weekly"]},
                "scheduleTime": {"type": "string", "description": "UTC time in HH:MM, for example 09:00."},
                "scheduleDayOfWeek": {"type": "integer", "minimum": 0, "maximum": 6},
                "triggerConfig": {"type": "object", "additionalProperties": True},
                "judgeImplementation": {"type": "string"},
            },
            "required": ["title", "prompt"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_update_work_item",
        "description": "Update an existing scoped work item. Use when the user asks to change a scheduled task, prompt, status, budget, schedule, or ownership fields.",
        "parameters": {
            "type": "object",
            "properties": {"workItemId": {"type": "string"}, "updates": {"type": "object", "additionalProperties": True}},
            "required": ["workItemId", "updates"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_run_work_item",
        "description": "Run a scoped work item now.",
        "parameters": {
            "type": "object",
            "properties": {
                "workItemId": {"type": "string"},
                "browserEnabled": {"type": "boolean"},
                "browserMode": {"type": "string", "enum": ["visible", "headless"]},
                "maxCreditsPerRun": {"type": "number", "minimum": 0},
            },
            "required": ["workItemId"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_delete_work_item",
        "description": "Delete a scoped work item. Use only when the user explicitly asks to delete/remove a work item.",
        "parameters": {"type": "object", "properties": {"workItemId": {"type": "string"}}, "required": ["workItemId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_rejudge_work_item",
        "description": "Rejudge an existing work item that has run results.",
        "parameters": {"type": "object", "properties": {"workItemId": {"type": "string"}}, "required": ["workItemId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_work_boards",
        "description": "List work boards for the scoped company.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_create_work_board",
        "description": "Create a work board for the scoped company.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_create_connector",
        "description": "Create a scoped connector. Do not ask for secrets in chat; create placeholders/config and direct the user to credentials forms for secret values.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string"},
                "category": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string"},
                "config": {"type": "object", "additionalProperties": True},
                "provider": {"type": "string"},
                "authRequired": {"type": "boolean"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_update_connector",
        "description": "Update connector metadata/config for a scoped connector. Never include raw secrets unless the user has explicitly provided them for credential setup.",
        "parameters": {
            "type": "object",
            "properties": {"connectorId": {"type": "string"}, "updates": {"type": "object", "additionalProperties": True}},
            "required": ["connectorId", "updates"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_test_connector",
        "description": "Run connector validation/test for a scoped connector.",
        "parameters": {"type": "object", "properties": {"connectorId": {"type": "string"}}, "required": ["connectorId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_delete_connector",
        "description": "Delete a scoped connector. Use only when the user explicitly asks to delete/remove it.",
        "parameters": {"type": "object", "properties": {"connectorId": {"type": "string"}}, "required": ["connectorId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_publish_connector_tools",
        "description": "Publish default callable tools for a scoped connector.",
        "parameters": {"type": "object", "properties": {"connectorId": {"type": "string"}}, "required": ["connectorId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_credentials",
        "description": "List scoped credentials with masked values only. Use for questions about configured secrets, missing credentials, credential names, connector auth status, or what credentials exist. Never exposes raw values.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_create_credential",
        "description": "Create a scoped encrypted credential only when the user explicitly provides the secret value in the current request. Prefer directing users to Settings/Credentials for secret entry. Output remains masked.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "value": {"type": "string"}, "type": {"type": "string"}, "createdFor": {"type": "string"}, "metadata": {"type": "object", "additionalProperties": True}},
            "required": ["name", "value"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_update_credential",
        "description": "Update scoped credential metadata/name/value. Use only when the user explicitly requests it.",
        "parameters": {"type": "object", "properties": {"credentialId": {"type": "string"}, "updates": {"type": "object", "additionalProperties": True}}, "required": ["credentialId", "updates"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_delete_credential",
        "description": "Delete a scoped credential. Use only when explicitly requested.",
        "parameters": {"type": "object", "properties": {"credentialId": {"type": "string"}}, "required": ["credentialId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_api_keys",
        "description": "List account API keys as masked prefixes/metadata when API key management is enabled. Use for Settings/API key inventory, not for runtime connector credentials.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_create_api_key",
        "description": "Create an API key for Studio API access, but redact the raw secret from assistant output/history. Prefer Settings/API Keys when the user needs to copy the one-time secret.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_rename_api_key",
        "description": "Rename an owned API key.",
        "parameters": {"type": "object", "properties": {"keyId": {"type": "string"}, "name": {"type": "string"}}, "required": ["keyId", "name"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_delete_api_key",
        "description": "Delete an owned API key. Use only when explicitly requested.",
        "parameters": {"type": "object", "properties": {"keyId": {"type": "string"}}, "required": ["keyId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_browser_profiles",
        "description": "List browser profiles for persistent browser login/session state. Use for Settings/Browser Profiles and when users ask which profile an agent/eval can use.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_create_browser_profile",
        "description": "Create a browser profile for persistent login/browser state.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "provider": {"type": "string", "enum": ["", "local", "browserbase", "auto"]}}, "required": ["name"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_rename_browser_profile",
        "description": "Rename an owned browser profile.",
        "parameters": {"type": "object", "properties": {"profileId": {"type": "string"}, "name": {"type": "string"}}, "required": ["profileId", "name"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_delete_browser_profile",
        "description": "Delete an owned browser profile. Use only when explicitly requested.",
        "parameters": {"type": "object", "properties": {"profileId": {"type": "string"}}, "required": ["profileId"], "additionalProperties": False},
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
        "name": "studio_approve_approval",
        "description": "Approve a pending approval owned by the authenticated user. Use only when the user explicitly asks to approve.",
        "parameters": {"type": "object", "properties": {"approvalId": {"type": "string"}, "reason": {"type": "string"}}, "required": ["approvalId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_reject_approval",
        "description": "Reject a pending approval owned by the authenticated user. Use only when the user explicitly asks to reject.",
        "parameters": {"type": "object", "properties": {"approvalId": {"type": "string"}, "reason": {"type": "string"}}, "required": ["approvalId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_knowledge_documents",
        "description": "List knowledge documents for the scoped company. Use for questions about uploaded docs, indexed knowledge, or grounding sources.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_create_vector_database",
        "description": "Create a vector database for scoped company knowledge.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "provider": {"type": "string"}, "collectionName": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_save_knowledge_document_from_url",
        "description": "Download an http(s) URL and save it as a scoped knowledge document.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "filename": {"type": "string"}, "vectorDatabaseId": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_delete_knowledge_document",
        "description": "Delete a scoped knowledge document. Use only when the user explicitly asks to delete/remove it.",
        "parameters": {"type": "object", "properties": {"documentId": {"type": "string"}}, "required": ["documentId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_artifacts",
        "description": "List created artifacts for the scoped company. Use for questions about documents, HTML/React/SVG artifacts, diagrams, exports, or generated files.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_assistant_conversations",
        "description": "List Automata assistant chat conversations for the authenticated user and scoped company. Use when the user asks about Automata chat history or which assistant chats exist.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_get_assistant_memory",
        "description": "Read compact long-term Automata memory built from previous assistant conversations for this user and company. Use when the user asks what Automata remembers, past context, prior decisions, or why the assistant should know previous chats.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_rebuild_assistant_memory",
        "description": "Queue an async job that summarizes previous Automata conversations and merges them into compact assistant memory. Use when the user asks to remember/summarize all chats, refresh memory, or give Automata knowledge of past conversations.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_delete_assistant_conversations",
        "description": "Delete Automata assistant chat conversations for the authenticated user and scoped company. Use only when the user explicitly asks to delete, clear, or remove Automata chat history. For deleteAll=true, the current conversation is preserved so the deletion result can be saved.",
        "parameters": {
            "type": "object",
            "properties": {
                "conversationIds": {"type": "array", "items": {"type": "string"}},
                "deleteAll": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_create_agent",
        "description": "Create an AgentConfig for the scoped company.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "websiteUrl": {"type": "string"},
                "successCriteria": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "browserEnabled": {"type": "boolean"},
                "browserMode": {"type": "string", "enum": ["visible", "headless"]},
                "maxCreditsPerRun": {"type": "number", "minimum": 0},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_update_agent_runtime_settings",
        "description": "Update browser/runtime settings for an AgentConfig.",
        "parameters": {
            "type": "object",
            "properties": {
                "agentId": {"type": "string"},
                "browserEnabled": {"type": "boolean"},
                "browserMode": {"type": "string", "enum": ["visible", "headless"]},
                "maxCreditsPerRun": {"type": "number", "minimum": 0},
            },
            "required": ["agentId"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_run_agent_task",
        "description": "Run a prompt against selected or all scoped AgentConfigs.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "target": {"type": "string", "enum": ["selected", "all"]},
                "agentId": {"type": "string"},
                "browserEnabled": {"type": "boolean"},
                "browserMode": {"type": "string", "enum": ["visible", "headless"]},
                "maxCreditsPerRun": {"type": "number", "minimum": 0},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_update_tool_approval",
        "description": "Set approval mode for a callable tool. approval must be always, auto, or never.",
        "parameters": {"type": "object", "properties": {"toolId": {"type": "string"}, "approval": {"type": "string", "enum": ["always", "auto", "never"]}}, "required": ["toolId", "approval"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_update_skill_approval",
        "description": "Set approval mode for a skill. approval must be always, auto, or never.",
        "parameters": {"type": "object", "properties": {"skillId": {"type": "string"}, "approval": {"type": "string", "enum": ["always", "auto", "never"]}}, "required": ["skillId", "approval"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_test_tool",
        "description": "Run a scoped callable tool test with arguments.",
        "parameters": {"type": "object", "properties": {"toolId": {"type": "string"}, "arguments": {"type": "object", "additionalProperties": True}}, "required": ["toolId"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_promote_trajectory_to_skill",
        "description": "Promote an approved/reviewed trajectory into a callable skill.",
        "parameters": {
            "type": "object",
            "properties": {"trajectoryId": {"type": "string"}, "name": {"type": "string"}, "whenToUse": {"type": "string"}, "permissions": {"type": "object", "additionalProperties": True}, "riskPolicy": {"type": "string"}},
            "required": ["trajectoryId"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "studio_get_account_info",
        "description": "Read authenticated account info and saved user instructions.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_update_account_instructions",
        "description": "Update saved account-level user instructions.",
        "parameters": {"type": "object", "properties": {"instructions": {"type": "string"}}, "required": ["instructions"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_get_analytics_summary",
        "description": "Get analytics for sessions and credit usage over 24h, 7d, 30d, or 90d. Use for spending, credits used, usage by source, usage over time, session counts, and limits diagnostics.",
        "parameters": {"type": "object", "properties": {"range": {"type": "string", "enum": ["24h", "7d", "30d", "90d"]}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_list_usage_events",
        "description": "List recent raw usage/credit events for the account.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "studio_get_billing_plan_status",
        "description": "Explain current billing/plan support and available frontend plans. Use for subscription, plan, wallet, payment, limits, or billing questions. It reports that backend billing is not wired when applicable.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
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
        self.current_conversation_id = ""

    async def assistant_settings(self) -> dict[str, Any]:
        model = default_assistant_model()
        updated_at = ""
        if self.context.company_id:
            try:
                company = await companies_collection.find_one(
                    {"email": self.context.email, "companyId": self.context.company_id},
                    {"_id": 0, "assistantSettings": 1},
                )
            except Exception:
                company = None
            settings = company.get("assistantSettings") if isinstance(company, dict) and isinstance(company.get("assistantSettings"), dict) else {}
            stored_model = str(settings.get("model") or "")
            if stored_model:
                try:
                    model = normalize_assistant_model(stored_model)
                except HTTPException:
                    model = default_assistant_model()
            updated_at = str(settings.get("updatedAt") or "")
        return {
            "model": model,
            "models": [
                {"value": "gpt-5-mini", "label": "GPT-5 mini"},
                {"value": "gpt-5.4", "label": "GPT-5.4"},
            ],
            "companyId": self.context.company_id,
            "updatedAt": updated_at,
        }

    async def update_assistant_settings(self, *, model: str) -> dict[str, Any]:
        if not self.context.company_id:
            raise HTTPException(status_code=400, detail="companyId is required")
        clean_model = normalize_assistant_model(model)
        now = now_iso()
        result = await companies_collection.update_one(
            {"email": self.context.email, "companyId": self.context.company_id},
            {"$set": {"assistantSettings.model": clean_model, "assistantSettings.updatedAt": now, "updatedAt": now}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Company not found")
        return await self.assistant_settings()

    async def create_conversation(self, seed_prompt: str = "") -> dict[str, Any]:
        now = now_iso()
        messages = []
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
            "assistantModel": (await self.assistant_settings()).get("model", default_assistant_model()),
            "messages": messages,
            "draft": draft,
            "createdAt": now,
            "updatedAt": now,
        }
        await assistant_conversations_collection.insert_one(doc)
        return conversation_payload(doc)

    async def load_owned_conversation(self, conversation_id: str) -> dict[str, Any]:
        query = {"conversationId": conversation_id, "email": self.context.email}
        if self.context.company_id:
            query["companyId"] = self.context.company_id
        doc = await assistant_conversations_collection.find_one(query, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Assistant conversation not found")
        return doc

    async def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return conversation_payload(await self.load_owned_conversation(conversation_id))

    async def list_conversations(self, *, limit: int = 30) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"email": self.context.email, "companyId": self.context.company_id or ""}
        cursor = assistant_conversations_collection.find(query, {"_id": 0}).sort("updatedAt", -1).limit(max(1, min(limit, 100)))
        docs = await cursor.to_list(length=max(1, min(limit, 100)))
        return [conversation_summary(doc) for doc in docs]

    async def send_message(self, conversation_id: str, message: str) -> dict[str, Any]:
        doc = await self.load_owned_conversation(conversation_id)
        self.current_conversation_id = conversation_id
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
        memory_text = ""
        try:
            memory = await self.tools.get_assistant_memory() if hasattr(self.tools, "get_assistant_memory") else None
            if isinstance(memory, dict) and str(memory.get("summary") or "").strip():
                memory_text = str(memory.get("summary") or "").strip()[:2500]
        except Exception:
            memory_text = ""
        instructions = self._llm_instructions(active_mode, memory_text=memory_text)
        model = (await self.assistant_settings()).get("model", default_assistant_model())

        response = await client.responses.create(
            **self._llm_request(model=model, instructions=instructions, input_items=input_items)
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
                model=model,
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

    def _llm_request(self, *, model: str, instructions: str, input_items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": normalize_assistant_model(model),
            "instructions": instructions,
            "input": input_items,
            "tools": ASSISTANT_FUNCTION_TOOLS,
            "reasoning": {"effort": os.getenv("AUTOMATA_ASSISTANT_REASONING_EFFORT", ASSISTANT_REASONING_EFFORT)},
            "text": {"verbosity": os.getenv("AUTOMATA_ASSISTANT_TEXT_VERBOSITY", ASSISTANT_TEXT_VERBOSITY)},
            "max_output_tokens": int(os.getenv("AUTOMATA_ASSISTANT_MAX_OUTPUT_TOKENS", str(ASSISTANT_MAX_OUTPUT_TOKENS))),
        }

    def _llm_instructions(self, mode: AssistantMode, *, memory_text: str = "") -> str:
        context_lines = [
            "Current user context:",
            f"- email: {self.context.email}",
            f"- companyId: {self.context.company_id or '(none selected)'}",
            f"- mode: {mode}",
        ]
        if self.context.route:
            context_lines.append(f"- route: {self.context.route}")
        visible_keys = sorted((self.context.visible_state or {}).keys())[:12]
        if visible_keys:
            context_lines.append(f"- visibleState keys: {', '.join(visible_keys)}")
        memory_block = ""
        if memory_text:
            memory_block = "Relevant long-term Automata memory from previous conversations:\n" + memory_text
        return "\n\n".join(
            [item for item in [
                system_prompt(mode),
                "\n".join(context_lines),
                memory_block,
                "Tool policy: use tools for current data or actions. Never claim create/update/delete/run/approve/reject/publish/test succeeded unless a tool returned success or a concrete id/result. Reads do not need confirmation. Destructive actions, real external sends, and secret changes need an explicit user request. Ask at most one concise clarification when required fields are missing.",
                "Secrets policy: never reveal raw secrets. Do not ask users to paste secrets if a Settings credential form is better. If a user provides a secret explicitly, use credential tools and keep outputs masked.",
                "Action hints: create scheduled work with studio_create_work_item after details/confirmation; create entities from OpenAPI with studio_generate_entities_from_openapi apply=true only when asked to create; clear Automata chat history with studio_delete_assistant_conversations while preserving the current conversation; refresh past-chat memory with studio_rebuild_assistant_memory.",
                "Answer concisely with concrete resource names/ids from tools. If a tool returns empty data, say so and suggest the next useful action.",
            ] if item]
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
        if name == "studio_create_connector":
            connector_name = str(arguments.get("name") or "").strip()
            if not connector_name:
                return {"error": "name is required"}
            return await self.tools.create_connector(
                name=connector_name,
                connector_type=str(arguments.get("type") or "api"),
                category=str(arguments.get("category") or "software"),
                description=str(arguments.get("description") or ""),
                status=str(arguments.get("status") or "not_connected"),
                config=arguments.get("config") if isinstance(arguments.get("config"), dict) else {},
                provider=str(arguments.get("provider") or ""),
                auth_required=arguments.get("authRequired") if isinstance(arguments.get("authRequired"), bool) else None,
            )
        if name == "studio_update_connector":
            connector_id = str(arguments.get("connectorId") or arguments.get("connector_id") or "").strip()
            updates = arguments.get("updates") if isinstance(arguments.get("updates"), dict) else {}
            if not connector_id or not updates:
                return {"error": "connectorId and updates are required"}
            return await self.tools.update_connector(connector_id, updates)
        if name == "studio_test_connector":
            connector_id = str(arguments.get("connectorId") or arguments.get("connector_id") or "").strip()
            if not connector_id:
                return {"error": "connectorId is required"}
            return await self.tools.test_connector(connector_id)
        if name == "studio_delete_connector":
            connector_id = str(arguments.get("connectorId") or arguments.get("connector_id") or "").strip()
            if not connector_id:
                return {"error": "connectorId is required"}
            return await self.tools.delete_connector(connector_id)
        if name == "studio_publish_connector_tools":
            connector_id = str(arguments.get("connectorId") or arguments.get("connector_id") or "").strip()
            if not connector_id:
                return {"error": "connectorId is required"}
            return await self.tools.publish_connector_tools(connector_id)
        if name == "studio_list_credentials":
            return {"credentials": await self.tools.list_credentials(limit=min(limit, 100))}
        if name == "studio_create_credential":
            credential_name = str(arguments.get("name") or "").strip()
            value = str(arguments.get("value") or "")
            if not credential_name or not value:
                return {"error": "name and value are required"}
            return await self.tools.create_credential(
                name=credential_name,
                value=value,
                credential_type=str(arguments.get("type") or "token"),
                created_for=str(arguments.get("createdFor") or arguments.get("created_for") or "connector"),
                metadata=arguments.get("metadata") if isinstance(arguments.get("metadata"), dict) else {},
            )
        if name == "studio_update_credential":
            credential_id = str(arguments.get("credentialId") or arguments.get("credential_id") or "").strip()
            updates = arguments.get("updates") if isinstance(arguments.get("updates"), dict) else {}
            if not credential_id or not updates:
                return {"error": "credentialId and updates are required"}
            return await self.tools.update_credential(credential_id, updates)
        if name == "studio_delete_credential":
            credential_id = str(arguments.get("credentialId") or arguments.get("credential_id") or "").strip()
            if not credential_id:
                return {"error": "credentialId is required"}
            return await self.tools.delete_credential(credential_id)
        if name == "studio_list_api_keys":
            return await self.tools.list_api_keys()
        if name == "studio_create_api_key":
            key_name = str(arguments.get("name") or "").strip()
            if not key_name:
                return {"error": "name is required"}
            return await self.tools.create_api_key(key_name)
        if name == "studio_rename_api_key":
            key_id = str(arguments.get("keyId") or arguments.get("key_id") or "").strip()
            key_name = str(arguments.get("name") or "").strip()
            if not key_id or not key_name:
                return {"error": "keyId and name are required"}
            return await self.tools.rename_api_key(key_id, key_name)
        if name == "studio_delete_api_key":
            key_id = str(arguments.get("keyId") or arguments.get("key_id") or "").strip()
            if not key_id:
                return {"error": "keyId is required"}
            return await self.tools.delete_api_key(key_id)
        if name == "studio_list_browser_profiles":
            return {"profiles": await self.tools.list_browser_profiles(limit=min(limit, 100))}
        if name == "studio_create_browser_profile":
            profile_name = str(arguments.get("name") or "").strip()
            if not profile_name:
                return {"error": "name is required"}
            return await self.tools.create_browser_profile(profile_name, provider=str(arguments.get("provider") or ""))
        if name == "studio_rename_browser_profile":
            profile_id = str(arguments.get("profileId") or arguments.get("profile_id") or "").strip()
            profile_name = str(arguments.get("name") or "").strip()
            if not profile_id or not profile_name:
                return {"error": "profileId and name are required"}
            return await self.tools.rename_browser_profile(profile_id, profile_name)
        if name == "studio_delete_browser_profile":
            profile_id = str(arguments.get("profileId") or arguments.get("profile_id") or "").strip()
            if not profile_id:
                return {"error": "profileId is required"}
            return await self.tools.delete_browser_profile(profile_id)
        if name == "studio_list_capabilities":
            return await self.tools.list_capabilities(limit=min(limit, 50))
        if name == "studio_list_agents":
            return {"agents": await self.tools.list_agents(limit=min(limit, 30))}
        if name == "studio_create_agent":
            agent_name = str(arguments.get("name") or "").strip()
            if not agent_name:
                return {"error": "name is required"}
            tasks = arguments.get("tasks") if isinstance(arguments.get("tasks"), list) else []
            return await self.tools.create_agent(
                name=agent_name,
                website_url=str(arguments.get("websiteUrl") or arguments.get("website_url") or ""),
                success_criteria=str(arguments.get("successCriteria") or arguments.get("success_criteria") or ""),
                tasks=[task for task in tasks if isinstance(task, dict)],
                browser_enabled=bool(arguments.get("browserEnabled", True)),
                browser_mode=str(arguments.get("browserMode") or "visible"),
                max_credits_per_run=float(arguments.get("maxCreditsPerRun") or 5.0),
            )
        if name == "studio_update_agent_runtime_settings":
            agent_id = str(arguments.get("agentId") or arguments.get("agent_id") or "").strip()
            if not agent_id:
                return {"error": "agentId is required"}
            return await self.tools.update_agent_runtime_settings(
                agent_id,
                browser_enabled=bool(arguments.get("browserEnabled", True)),
                browser_mode=str(arguments.get("browserMode") or "visible"),
                max_credits_per_run=float(arguments.get("maxCreditsPerRun") or 5.0),
            )
        if name == "studio_run_agent_task":
            prompt = str(arguments.get("prompt") or "").strip()
            if not prompt:
                return {"error": "prompt is required"}
            return await self.tools.run_agent_task(
                prompt=prompt,
                target=str(arguments.get("target") or "selected"),
                agent_id=str(arguments.get("agentId") or arguments.get("agent_id") or ""),
                browser_enabled=arguments.get("browserEnabled") if isinstance(arguments.get("browserEnabled"), bool) else None,
                browser_mode=str(arguments.get("browserMode") or "visible"),
                max_credits_per_run=float(arguments.get("maxCreditsPerRun") or 5.0),
            )
        if name == "studio_list_work_items":
            return {"workItems": await self.tools.list_work_items(limit=min(limit, 50))}
        if name == "studio_create_work_item":
            title = str(arguments.get("title") or "").strip()
            prompt = str(arguments.get("prompt") or "").strip()
            if not title or not prompt:
                return {"error": "title and prompt are required"}
            return await self.tools.create_work_item(
                title=title,
                prompt=prompt,
                success_criteria=str(arguments.get("successCriteria") or arguments.get("success_criteria") or ""),
                agent_id=str(arguments.get("agentId") or arguments.get("agent_id") or ""),
                agent_name=str(arguments.get("agentName") or arguments.get("agent_name") or ""),
                run_target=str(arguments.get("runTarget") or arguments.get("run_target") or "all"),
                browser_enabled=bool(arguments.get("browserEnabled", True)),
                browser_mode=str(arguments.get("browserMode") or arguments.get("browser_mode") or "headless"),
                max_credits_per_run=float(arguments.get("maxCreditsPerRun") or arguments.get("max_credits_per_run") or 5.0),
                max_budget_credits=(
                    float(arguments.get("maxBudgetCredits") or arguments.get("max_budget_credits"))
                    if arguments.get("maxBudgetCredits") is not None or arguments.get("max_budget_credits") is not None
                    else None
                ),
                max_steps=int(arguments.get("maxSteps") or arguments.get("max_steps") or 8),
                trigger_type=str(arguments.get("triggerType") or arguments.get("trigger_type") or "manual"),
                schedule_frequency=str(arguments.get("scheduleFrequency") or arguments.get("schedule_frequency") or "none"),
                schedule_time=str(arguments.get("scheduleTime") or arguments.get("schedule_time") or "09:00"),
                schedule_day_of_week=int(arguments.get("scheduleDayOfWeek") or arguments.get("schedule_day_of_week") or 1),
                trigger_config=arguments.get("triggerConfig") if isinstance(arguments.get("triggerConfig"), dict) else {},
                judge_implementation=str(arguments.get("judgeImplementation") or arguments.get("judge_implementation") or "llm"),
            )
        if name == "studio_update_work_item":
            work_item_id = str(arguments.get("workItemId") or arguments.get("work_item_id") or "").strip()
            updates = arguments.get("updates") if isinstance(arguments.get("updates"), dict) else {}
            if not work_item_id or not updates:
                return {"error": "workItemId and updates are required"}
            return await self.tools.update_work_item(work_item_id, updates)
        if name == "studio_run_work_item":
            work_item_id = str(arguments.get("workItemId") or arguments.get("work_item_id") or "").strip()
            if not work_item_id:
                return {"error": "workItemId is required"}
            return await self.tools.run_work_item(
                work_item_id,
                browser_enabled=arguments.get("browserEnabled") if isinstance(arguments.get("browserEnabled"), bool) else None,
                browser_mode=str(arguments.get("browserMode")) if arguments.get("browserMode") is not None else None,
                max_credits_per_run=float(arguments.get("maxCreditsPerRun")) if arguments.get("maxCreditsPerRun") is not None else None,
            )
        if name == "studio_delete_work_item":
            work_item_id = str(arguments.get("workItemId") or arguments.get("work_item_id") or "").strip()
            if not work_item_id:
                return {"error": "workItemId is required"}
            return await self.tools.delete_work_item(work_item_id)
        if name == "studio_rejudge_work_item":
            work_item_id = str(arguments.get("workItemId") or arguments.get("work_item_id") or "").strip()
            if not work_item_id:
                return {"error": "workItemId is required"}
            return await self.tools.rejudge_work_item(work_item_id)
        if name == "studio_list_work_boards":
            return {"boards": await self.tools.list_work_boards()}
        if name == "studio_create_work_board":
            board_name = str(arguments.get("name") or "").strip()
            if not board_name:
                return {"error": "name is required"}
            return await self.tools.create_work_board(board_name)
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
        if name == "studio_approve_approval":
            approval_id = str(arguments.get("approvalId") or arguments.get("approval_id") or "").strip()
            if not approval_id:
                return {"error": "approvalId is required"}
            return await self.tools.approve_approval(approval_id, reason=str(arguments.get("reason") or ""))
        if name == "studio_reject_approval":
            approval_id = str(arguments.get("approvalId") or arguments.get("approval_id") or "").strip()
            if not approval_id:
                return {"error": "approvalId is required"}
            return await self.tools.reject_approval(approval_id, reason=str(arguments.get("reason") or ""))
        if name == "studio_list_knowledge_documents":
            return {"documents": await self.tools.list_knowledge_documents(limit=min(limit, 50))}
        if name == "studio_create_vector_database":
            db_name = str(arguments.get("name") or "").strip()
            if not db_name:
                return {"error": "name is required"}
            return await self.tools.create_vector_database(
                db_name,
                provider=str(arguments.get("provider") or "local"),
                collection_name=str(arguments.get("collectionName") or arguments.get("collection_name") or ""),
            )
        if name == "studio_save_knowledge_document_from_url":
            url = str(arguments.get("url") or "").strip()
            if not url:
                return {"error": "url is required"}
            return await self.tools.save_knowledge_document_from_url(
                url=url,
                filename=str(arguments.get("filename") or ""),
                vector_database_id=str(arguments.get("vectorDatabaseId") or arguments.get("vector_database_id") or ""),
            )
        if name == "studio_delete_knowledge_document":
            document_id = str(arguments.get("documentId") or arguments.get("document_id") or "").strip()
            if not document_id:
                return {"error": "documentId is required"}
            return await self.tools.delete_knowledge_document(document_id)
        if name == "studio_list_artifacts":
            return {"artifacts": await self.tools.list_artifacts(limit=min(limit, 50))}
        if name == "studio_update_tool_approval":
            tool_id = str(arguments.get("toolId") or arguments.get("tool_id") or "").strip()
            if not tool_id:
                return {"error": "toolId is required"}
            return await self.tools.update_tool_approval(tool_id, approval=str(arguments.get("approval") or ""))
        if name == "studio_update_skill_approval":
            skill_id = str(arguments.get("skillId") or arguments.get("skill_id") or "").strip()
            if not skill_id:
                return {"error": "skillId is required"}
            return await self.tools.update_skill_approval(skill_id, approval=str(arguments.get("approval") or ""))
        if name == "studio_test_tool":
            tool_id = str(arguments.get("toolId") or arguments.get("tool_id") or "").strip()
            if not tool_id:
                return {"error": "toolId is required"}
            return await self.tools.test_tool(tool_id, arguments=arguments.get("arguments") if isinstance(arguments.get("arguments"), dict) else {})
        if name == "studio_promote_trajectory_to_skill":
            trajectory_id = str(arguments.get("trajectoryId") or arguments.get("trajectory_id") or "").strip()
            if not trajectory_id:
                return {"error": "trajectoryId is required"}
            return await self.tools.promote_trajectory_to_skill(
                trajectory_id,
                name=str(arguments.get("name") or ""),
                when_to_use=str(arguments.get("whenToUse") or arguments.get("when_to_use") or ""),
                permissions=arguments.get("permissions") if isinstance(arguments.get("permissions"), dict) else {},
                risk_policy=str(arguments.get("riskPolicy") or arguments.get("risk_policy") or "human_approval_for_writes"),
            )
        if name == "studio_get_account_info":
            return await self.tools.get_account_info()
        if name == "studio_update_account_instructions":
            return await self.tools.update_account_instructions(str(arguments.get("instructions") or ""))
        if name == "studio_get_analytics_summary":
            return await self.tools.analytics_summary(range_key=str(arguments.get("range") or "30d"))
        if name == "studio_list_usage_events":
            return {"usageEvents": await self.tools.usage_events(limit=min(limit, 100))}
        if name == "studio_get_billing_plan_status":
            return await self.tools.billing_plan_status()
        if name == "studio_list_assistant_conversations":
            return {"conversations": await self.tools.list_assistant_conversations(limit=min(limit, 50))}
        if name == "studio_get_assistant_memory":
            return await self.tools.get_assistant_memory()
        if name == "studio_rebuild_assistant_memory":
            return await self.tools.rebuild_assistant_memory(limit=min(limit, 500))
        if name == "studio_delete_assistant_conversations":
            conversation_ids = arguments.get("conversationIds") or arguments.get("conversation_ids") or []
            if not isinstance(conversation_ids, list):
                conversation_ids = []
            return await self.tools.delete_assistant_conversations(
                conversation_ids=conversation_ids,
                delete_all=bool(arguments.get("deleteAll") or arguments.get("delete_all")),
                exclude_conversation_id=self.current_conversation_id,
            )
        return {"error": f"Unknown Studio tool: {name}"}

    def _tool_event_summary(self, name: str, output: dict[str, Any]) -> str:
        if name == "studio_snapshot":
            counts = output.get("counts") if isinstance(output.get("counts"), dict) else {}
            readiness = ((output.get("operatingState") or {}).get("readiness") or {}) if isinstance(output.get("operatingState"), dict) else {}
            score = readiness.get("score")
            score_text = f", readiness {int(float(score) * 100)}%" if isinstance(score, (int, float)) else ""
            return f"Loaded Studio operating state: {counts.get('companies', 0)} companies, {counts.get('connectors', 0)} connectors, {counts.get('tools', 0)} tools, {counts.get('skills', 0)} skills{score_text}."
        key = next((item for item in ("companies", "connectors", "agents", "workItems", "boards", "credentials", "apiKeys", "profiles", "usageEvents", "entities", "approvals", "documents", "artifacts", "conversations") if isinstance(output.get(item), list)), "")
        if key:
            return f"Loaded {len(output.get(key) or [])} {key}."
        if name in {"studio_create_connector", "studio_update_connector"}:
            connector = output.get("connector") if isinstance(output.get("connector"), dict) else {}
            verb = "Created" if name == "studio_create_connector" else "Updated"
            return f"{verb} connector {connector.get('name') or connector.get('connectorId') or ''}.".strip()
        if name == "studio_test_connector":
            return f"Connector test {'passed' if output.get('success') else 'failed'}."
        if name == "studio_delete_connector":
            return "Deleted connector." if output.get("success") else "Connector deletion failed."
        if name == "studio_publish_connector_tools":
            tools = output.get("tools") if isinstance(output.get("tools"), list) else []
            return f"Published {len(tools)} connector tool(s)."
        if name == "studio_create_credential":
            credential = output.get("credential") if isinstance(output.get("credential"), dict) else {}
            return f"Created credential {credential.get('name') or credential.get('credentialId') or ''}.".strip()
        if name == "studio_update_credential":
            credential = output.get("credential") if isinstance(output.get("credential"), dict) else {}
            return f"Updated credential {credential.get('name') or credential.get('credentialId') or ''}.".strip()
        if name == "studio_delete_credential":
            return "Deleted credential." if output.get("success") else "Credential deletion failed."
        if name == "studio_create_api_key":
            api_key = output.get("apiKey") if isinstance(output.get("apiKey"), dict) else {}
            return f"Created API key {api_key.get('name') or api_key.get('id') or ''} with secret redacted.".strip()
        if name == "studio_rename_api_key":
            return "Renamed API key." if output.get("success") else "API key rename failed."
        if name == "studio_delete_api_key":
            return "Deleted API key." if output.get("success") else "API key deletion failed."
        if name == "studio_create_browser_profile":
            profile = output.get("profile") if isinstance(output.get("profile"), dict) else {}
            return f"Created browser profile {profile.get('name') or profile.get('id') or ''}.".strip()
        if name == "studio_rename_browser_profile":
            return "Renamed browser profile." if output.get("success") else "Browser profile rename failed."
        if name == "studio_delete_browser_profile":
            return "Deleted browser profile." if output.get("success") else "Browser profile deletion failed."
        if name == "studio_create_agent":
            return f"Created agent {output.get('agentId') or output.get('agentConfigId') or ''}.".strip()
        if name == "studio_update_agent_runtime_settings":
            agent = output.get("agent") if isinstance(output.get("agent"), dict) else {}
            return f"Updated agent runtime settings for {agent.get('name') or agent.get('agentId') or ''}.".strip()
        if name == "studio_run_agent_task":
            results = output.get("results") if isinstance(output.get("results"), list) else []
            return f"Ran agent task against {len(results)} agent(s)."
        if name == "studio_create_work_item":
            work_item = output.get("workItem") if isinstance(output.get("workItem"), dict) else {}
            return f"Created work item {work_item.get('title') or work_item.get('workItemId') or ''}.".strip()
        if name == "studio_update_work_item":
            work_item = output.get("workItem") if isinstance(output.get("workItem"), dict) else {}
            return f"Updated work item {work_item.get('title') or work_item.get('workItemId') or ''}.".strip()
        if name == "studio_run_work_item":
            return f"Started work item run {output.get('runId') or ''}.".strip()
        if name == "studio_delete_work_item":
            return "Deleted work item." if output.get("success") else "Work item deletion failed."
        if name == "studio_rejudge_work_item":
            return "Rejudged work item." if output.get("success") else "Work item rejudge failed."
        if name == "studio_create_work_board":
            board = output.get("board") if isinstance(output.get("board"), dict) else {}
            return f"Created work board {board.get('name') or board.get('boardId') or ''}.".strip()
        if name == "studio_approve_approval":
            return "Approved request." if output.get("success") else "Approval failed."
        if name == "studio_reject_approval":
            return "Rejected request." if output.get("success") else "Rejection failed."
        if name == "studio_create_vector_database":
            db = output.get("vectorDatabase") if isinstance(output.get("vectorDatabase"), dict) else {}
            return f"Created vector database {db.get('name') or db.get('vectorDatabaseId') or ''}.".strip()
        if name == "studio_save_knowledge_document_from_url":
            doc = output.get("document") if isinstance(output.get("document"), dict) else {}
            return f"Saved knowledge document {doc.get('filename') or doc.get('documentId') or ''}.".strip()
        if name == "studio_delete_knowledge_document":
            return "Deleted knowledge document." if output.get("success") else "Knowledge document deletion failed."
        if name == "studio_update_tool_approval":
            return "Updated tool approval mode." if output.get("success") else "Tool approval update failed."
        if name == "studio_update_skill_approval":
            return "Updated skill approval mode." if output.get("success") else "Skill approval update failed."
        if name == "studio_test_tool":
            return f"Tool test {'passed' if output.get('success') else 'failed'}."
        if name == "studio_promote_trajectory_to_skill":
            skill = output.get("skill") if isinstance(output.get("skill"), dict) else {}
            return f"Promoted trajectory to skill {skill.get('name') or skill.get('skillId') or ''}.".strip()
        if name == "studio_get_account_info":
            user = output.get("user") if isinstance(output.get("user"), dict) else {}
            return f"Loaded account info for {user.get('email') or ''}.".strip()
        if name == "studio_update_account_instructions":
            return "Updated account instructions." if output.get("user") else "Account instructions update failed."
        if name == "studio_get_analytics_summary":
            credits = output.get("credits") if isinstance(output.get("credits"), dict) else {}
            return f"Loaded analytics: {credits.get('total_usage', 0)} credits used."
        if name == "studio_get_billing_plan_status":
            return "Loaded billing and plan status."
        if name == "studio_get_assistant_memory":
            return "Loaded Automata conversation memory." if output.get("exists") else "No Automata conversation memory found."
        if name == "studio_rebuild_assistant_memory":
            return f"Queued Automata memory rebuild job {output.get('jobId') or ''}.".strip()
        if name == "studio_delete_assistant_conversations":
            return f"Deleted {int(output.get('deleted') or 0)} Automata conversation(s)."
        if name == "studio_generate_entities_from_openapi":
            return self._entity_generation_summary(output)
        if "tools" in output or "skills" in output:
            return f"Loaded {len(output.get('tools') or [])} tools and {len(output.get('skills') or [])} skills."
        return f"Ran {name}."

    def _snapshot_reply(self, snapshot: dict[str, Any]) -> str:
        counts = snapshot.get("counts", {})
        if not counts.get("companies"):
            return "You do not have a company configured yet. I can help you start onboarding and create the company, connectors, tasks, and first agent."
        operating_state = snapshot.get("operatingState") if isinstance(snapshot.get("operatingState"), dict) else {}
        readiness = operating_state.get("readiness") if isinstance(operating_state.get("readiness"), dict) else {}
        company_setup = operating_state.get("companySetup") if isinstance(operating_state.get("companySetup"), dict) else {}
        factory = operating_state.get("factory") if isinstance(operating_state.get("factory"), dict) else {}
        capability_map = operating_state.get("capabilityMap") if isinstance(operating_state.get("capabilityMap"), dict) else {}
        resource_map = operating_state.get("resourceMap") if isinstance(operating_state.get("resourceMap"), dict) else {}
        runtime = operating_state.get("runtime") if isinstance(operating_state.get("runtime"), dict) else {}
        work_orchestration = operating_state.get("workOrchestration") if isinstance(operating_state.get("workOrchestration"), dict) else {}
        studio_os_gate = operating_state.get("studioOsGate") if isinstance(operating_state.get("studioOsGate"), dict) else {}
        next_actions = operating_state.get("recommendedNextActions") if isinstance(operating_state.get("recommendedNextActions"), list) else []
        guidance = operating_state.get("automataGuidance") if isinstance(operating_state.get("automataGuidance"), dict) else {}
        score = readiness.get("score")
        score_text = f" Readiness is {int(float(score) * 100)}%." if isinstance(score, (int, float)) else ""
        studio_os_text = ""
        if studio_os_gate:
            surfaces = studio_os_gate.get("surfaces") if isinstance(studio_os_gate.get("surfaces"), dict) else {}
            studio_os_text = (
                f" Studio OS gate: {studio_os_gate.get('state', 'unknown')}, "
                f"{surfaces.get('ready', 0)}/{surfaces.get('total', 0)} surface(s) ready."
            )
            blockers = studio_os_gate.get("blockers") if isinstance(studio_os_gate.get("blockers"), list) else []
            if blockers:
                studio_os_text += f" First surface blocker: {blockers[0]}."
        company_setup_text = ""
        setup_gate = company_setup.get("setupGate") if isinstance(company_setup.get("setupGate"), dict) else {}
        integration = company_setup.get("integration") if isinstance(company_setup.get("integration"), dict) else {}
        if setup_gate:
            blockers = setup_gate.get("blockers") if isinstance(setup_gate.get("blockers"), list) else []
            company_setup_text = (
                f" Company Setup gate: {setup_gate.get('state', 'unknown')}, "
                f"{integration.get('systems', 0)} system(s), {integration.get('secrets', 0)} secret(s), "
                f"{len(integration.get('domainAllowlist') or [])} allowed domain(s)."
            )
            if blockers:
                company_setup_text += f" First setup blocker: {blockers[0]}."
        factory_text = ""
        connector_map = factory.get("connectorMap") if isinstance(factory.get("connectorMap"), dict) else {}
        if connector_map:
            factory_text = (
                f" Factory pipeline: {connector_map.get('entityMapped', 0)}/{connector_map.get('total', 0)} connector(s) entity-mapped, "
                f"{connector_map.get('typedToolReady', 0)} with typed tools, "
                f"{connector_map.get('candidateTasksReady', 0)} with candidate tasks."
            )
            if int(connector_map.get("hardenedToolCount") or 0) or int(connector_map.get("needsHardeningCount") or 0):
                factory_text += (
                    f" Tool hardening: {connector_map.get('hardenedToolCount', 0)} hardened, "
                    f"{connector_map.get('needsHardeningCount', 0)} need policy/entity/risk hardening."
                )
                hardening_gaps = connector_map.get("toolHardeningGaps") if isinstance(connector_map.get("toolHardeningGaps"), list) else []
                first_hardening_gap = hardening_gaps[0] if hardening_gaps and isinstance(hardening_gaps[0], dict) else {}
                if first_hardening_gap:
                    factory_text += f" First tool hardening gap: {first_hardening_gap.get('name') or 'runtime_policy'}."
            tool_gate = connector_map.get("toolProductionGate") if isinstance(connector_map.get("toolProductionGate"), dict) else {}
            if tool_gate:
                factory_text += (
                    f" Tool production gate: {tool_gate.get('state', 'unknown')}, "
                    f"{tool_gate.get('hardenedTools', 0)}/{tool_gate.get('totalTools', 0)} tool(s) hardened."
                )
            factory_gate = connector_map.get("factoryPipelineGate") if isinstance(connector_map.get("factoryPipelineGate"), dict) else {}
            if factory_gate:
                factory_text += f" Capability factory gate: {factory_gate.get('state', 'unknown')}."
            blocked_count = int(connector_map.get("entityPending") or 0) + int(connector_map.get("toolSynthesisPending") or 0) + int(connector_map.get("ingestionBlocked") or 0)
            if blocked_count:
                factory_text += (
                    f" Factory blockers: {connector_map.get('entityPending', 0)} entity pending, "
                    f"{connector_map.get('toolSynthesisPending', 0)} tool synthesis pending, "
                    f"{connector_map.get('ingestionBlocked', 0)} ingestion blocked."
                )
                gaps = connector_map.get("gaps") if isinstance(connector_map.get("gaps"), list) else []
                first_gap = gaps[0] if gaps and isinstance(gaps[0], dict) else {}
                if first_gap:
                    factory_text += f" First factory blocker: {first_gap.get('label') or first_gap.get('key') or 'connector discovery'}."
        task_contracts = capability_map.get("taskContracts") if isinstance(capability_map.get("taskContracts"), dict) else {}
        entity_map = capability_map.get("entityMap") if isinstance(capability_map.get("entityMap"), dict) else {}
        skills = capability_map.get("skills") if isinstance(capability_map.get("skills"), dict) else {}
        eval_gate = capability_map.get("evalGate") if isinstance(capability_map.get("evalGate"), dict) else {}
        eval_coverage = capability_map.get("evalCoverage") if isinstance(capability_map.get("evalCoverage"), dict) else {}
        benchmark_portfolio = capability_map.get("benchmarkPortfolio") if isinstance(capability_map.get("benchmarkPortfolio"), dict) else {}
        promotion_pipeline = capability_map.get("promotionPipeline") if isinstance(capability_map.get("promotionPipeline"), dict) else {}
        vertical_demos = capability_map.get("verticalDemos") if isinstance(capability_map.get("verticalDemos"), dict) else {}
        vertical_demo_gaps = capability_map.get("verticalDemoGaps") if isinstance(capability_map.get("verticalDemoGaps"), list) else []
        sla = work_orchestration.get("sla") if isinstance(work_orchestration.get("sla"), dict) else {}
        coverage_text = ""
        if task_contracts or skills:
            coverage_text = (
                f" Capability coverage: {task_contracts.get('ready', 0)}/{task_contracts.get('total', 0)} task contracts ready, "
                f"{skills.get('hardened', 0)}/{skills.get('total', 0)} skills hardened."
            )
            reproducibility = task_contracts.get("reproducibility") if isinstance(task_contracts.get("reproducibility"), dict) else {}
            if reproducibility:
                coverage_text += (
                    f" Task replayability: {reproducibility.get('readyForReplay', 0)}/{reproducibility.get('total', task_contracts.get('total', 0))} replay-ready."
                )
            if entity_map:
                coverage_text += (
                    f" Entity mapping: {entity_map.get('ready', 0)}/{entity_map.get('total', 0)} ready, "
                    f"{entity_map.get('toolBindingReady', 0)} runtime-bindable, "
                    f"{entity_map.get('withRelationships', 0)} with relationships."
                )
                blockers = entity_map.get("bindingBlockers") if isinstance(entity_map.get("bindingBlockers"), list) else []
                first_blocker = blockers[0] if blockers and isinstance(blockers[0], dict) else {}
                if first_blocker:
                    coverage_text += f" First entity blocker: {first_blocker.get('name') or 'mapping'}."
            packages = skills.get("packages") if isinstance(skills.get("packages"), dict) else {}
            if packages:
                coverage_text += (
                    f" Skill packages: {packages.get('publishable', 0)}/{packages.get('total', skills.get('total', 0))} publishable, "
                    f"{packages.get('ioContracts', 0)} with IO contracts, {packages.get('regressionSuites', 0)} with regressions, "
                    f"{packages.get('assets', packages.get('withAssets', 0))} with assets "
                    f"({packages.get('resources', packages.get('withResources', 0))} resources, "
                    f"{packages.get('scripts', packages.get('withScripts', 0))} scripts)."
                )
                release = packages.get("releaseReadiness") if isinstance(packages.get("releaseReadiness"), dict) else {}
                if release:
                    coverage_text += (
                        f" Skill releases: {release.get('published', 0)} published, "
                        f"{release.get('readyForPublish', 0)} ready for publish, {release.get('draft', 0)} draft."
                    )
                release_gate = packages.get("releaseGate") if isinstance(packages.get("releaseGate"), dict) else {}
                if release_gate:
                    coverage_text += f" Skill release gate: {release_gate.get('state', 'unknown')}."
            if eval_gate:
                coverage_text += (
                    f" Eval gates: {eval_gate.get('passing', 0)} passing, "
                    f"{eval_gate.get('blockedByRegression', 0)} blocked, {eval_gate.get('missing', 0)} missing regression."
                )
            if eval_coverage:
                connector_coverage = eval_coverage.get("connectors") if isinstance(eval_coverage.get("connectors"), dict) else {}
                entity_coverage = eval_coverage.get("entities") if isinstance(eval_coverage.get("entities"), dict) else {}
                skill_coverage = eval_coverage.get("skills") if isinstance(eval_coverage.get("skills"), dict) else {}
                coverage_text += (
                    f" Eval coverage: connectors {connector_coverage.get('covered', 0)}/{connector_coverage.get('total', 0)}, "
                    f"entities {entity_coverage.get('covered', 0)}/{entity_coverage.get('total', 0)}, "
                    f"skills {skill_coverage.get('covered', 0)}/{skill_coverage.get('total', 0)}."
                )
                coverage_gap = _coverage_gap_label(eval_coverage)
                if coverage_gap:
                    coverage_text += f" First eval coverage blocker: {coverage_gap}."
            if benchmark_portfolio:
                promotion_gate = benchmark_portfolio.get("promotionGate") if isinstance(benchmark_portfolio.get("promotionGate"), dict) else {}
                regression_gate = benchmark_portfolio.get("regressionGate") if isinstance(benchmark_portfolio.get("regressionGate"), dict) else {}
                eval_center_gate = benchmark_portfolio.get("evalCenterGate") if isinstance(benchmark_portfolio.get("evalCenterGate"), dict) else {}
                coverage_text += (
                    f" Benchmark portfolio: {benchmark_portfolio.get('benchmarks', 0)} benchmark(s), "
                    f"{benchmark_portfolio.get('tasks', 0)} task(s), promotion gate {promotion_gate.get('state', 'unknown')}."
                )
                if eval_center_gate:
                    task_coverage = eval_center_gate.get("taskCoverage") if isinstance(eval_center_gate.get("taskCoverage"), dict) else {}
                    coverage_text += (
                        f" Eval center gate: {eval_center_gate.get('state', 'unknown')}, "
                        f"{task_coverage.get('replayReady', 0)}/{task_coverage.get('total', 0)} replay-ready task(s)."
                    )
                if regression_gate:
                    coverage_text += (
                        f" Regression gate: {regression_gate.get('gatedCapabilities', 0)}/{regression_gate.get('totalCapabilities', 0)} "
                        f"capabilities gated, state {regression_gate.get('state', 'unknown')}."
                    )
                judge_gate = benchmark_portfolio.get("judgeStrategyGate") if isinstance(benchmark_portfolio.get("judgeStrategyGate"), dict) else {}
                if judge_gate:
                    coverage_text += (
                        f" Judge strategy gate: {judge_gate.get('state', 'unknown')}, "
                        f"{judge_gate.get('deterministic', 0)}/{judge_gate.get('total', 0)} deterministic, "
                        f"{judge_gate.get('stateful', 0)} stateful."
                    )
            if promotion_pipeline:
                pipeline_tasks = promotion_pipeline.get("tasks") if isinstance(promotion_pipeline.get("tasks"), dict) else {}
                pipeline_trajectories = promotion_pipeline.get("trajectories") if isinstance(promotion_pipeline.get("trajectories"), dict) else {}
                pipeline_skills = promotion_pipeline.get("skills") if isinstance(promotion_pipeline.get("skills"), dict) else {}
                coverage_text += (
                    f" Promotion pipeline: {pipeline_tasks.get('withTrajectory', 0)}/{pipeline_tasks.get('total', 0)} tasks with trajectories, "
                    f"{pipeline_trajectories.get('approved', 0)}/{pipeline_trajectories.get('total', 0)} trajectories approved, "
                    f"{pipeline_skills.get('withApprovedTrajectory', 0)}/{pipeline_skills.get('total', 0)} skills trajectory-linked."
                )
                if not promotion_pipeline.get("ready"):
                    gaps = promotion_pipeline.get("gaps") if isinstance(promotion_pipeline.get("gaps"), list) else []
                    first_gap = gaps[0] if gaps and isinstance(gaps[0], dict) else {}
                    if first_gap:
                        coverage_text += f" First promotion blocker: {first_gap.get('label') or first_gap.get('key') or 'promotion evidence'}."
            if vertical_demos:
                demo_items = vertical_demos.get("demos") if isinstance(vertical_demos.get("demos"), list) else []
                first_proof_blocked = next(
                    (
                        demo
                        for demo in demo_items
                        if isinstance(demo, dict)
                        and isinstance(demo.get("insuranceFlowProofGate"), dict)
                        and not (demo.get("insuranceFlowProofGate") or {}).get("ready")
                    ),
                    {},
                )
                coverage_text += (
                    f" Vertical demos: {vertical_demos.get('ready', 0)}/{vertical_demos.get('total', 0)} ready, "
                    f"{vertical_demos.get('enterpriseReady', 0)} enterprise-ready, "
                    f"{vertical_demos.get('smokeReady', 0)} smoke-ready, "
                    f"{vertical_demos.get('proofReady', 0)} proof-ready, "
                    f"{vertical_demos.get('proofBlocked', 0)} proof-blocked."
                )
                if vertical_demo_gaps:
                    first_gap = vertical_demo_gaps[0] if isinstance(vertical_demo_gaps[0], dict) else {}
                    coverage_text += f" First demo blocker: {first_gap.get('label') or first_gap.get('group') or 'operational evidence'}."
                if first_proof_blocked:
                    proof_gate = first_proof_blocked.get("insuranceFlowProofGate") or {}
                    missing = proof_gate.get("missing") if isinstance(proof_gate.get("missing"), list) else []
                    coverage_text += f" First proof blocker: {missing[0] if missing else proof_gate.get('state') or 'proof evidence'}."
        resource_text = ""
        if resource_map:
            resource_text = (
                f" Resource grounding: {resource_map.get('indexed', 0)}/{resource_map.get('total', 0)} indexed, "
                f"{resource_map.get('citable', 0)}/{resource_map.get('total', 0)} citable."
            )
            runtime_gate = resource_map.get("runtimeGate") if isinstance(resource_map.get("runtimeGate"), dict) else {}
            if runtime_gate:
                ready_resources = int(runtime_gate.get("ready") or 0)
                blocked_resources = int(runtime_gate.get("blocked") or 0)
                gated_resources = ready_resources + blocked_resources
                resource_text += (
                    f" Resource runtime gate: {ready_resources}/{gated_resources} ready, "
                    f"{blocked_resources} blocked."
                )
                blockers = runtime_gate.get("blockers") if isinstance(runtime_gate.get("blockers"), list) else []
                first_blocker = blockers[0] if blockers and isinstance(blockers[0], dict) else {}
                if first_blocker:
                    resource_text += f" First resource blocker: {first_blocker.get('name', 'resource governance')}."
        runtime_text = ""
        runtime_policy = runtime.get("runtimePolicyMap") if isinstance(runtime.get("runtimePolicyMap"), dict) else {}
        if runtime_policy:
            human = runtime_policy.get("humanApproval") if isinstance(runtime_policy.get("humanApproval"), dict) else {}
            classes = runtime_policy.get("runtimeClasses") if isinstance(runtime_policy.get("runtimeClasses"), dict) else {}
            runtime_text = (
                f" Runtime policy: browser default {runtime_policy.get('defaultBrowserUse', 'exception')}, "
                f"{classes.get('browserSessions', 0)} browser sessions, "
                f"write/send {'protected' if human.get('writesProtected') and human.get('sendsProtected') else 'incomplete'}."
            )
            class_gate = runtime_policy.get("runtimeClassGate") if isinstance(runtime_policy.get("runtimeClassGate"), dict) else {}
            if class_gate:
                runtime_text += f" Runtime class gate: {class_gate.get('state', 'unknown')}."
                class_blockers = class_gate.get("blockers") if isinstance(class_gate.get("blockers"), list) else []
                first_class_blocker = class_blockers[0] if class_blockers and isinstance(class_blockers[0], dict) else {}
                if first_class_blocker:
                    runtime_text += f" First runtime class blocker: {first_class_blocker.get('name') or 'runtime policy'}."
            approval_boundaries = runtime_policy.get("approvalBoundaries") if isinstance(runtime_policy.get("approvalBoundaries"), dict) else {}
            if approval_boundaries:
                missing_approvals = approval_boundaries.get("missingObservedApproval") if isinstance(approval_boundaries.get("missingObservedApproval"), list) else []
                runtime_text += (
                    f" Side-effect approvals: {'protected' if approval_boundaries.get('sideEffectsProtected') else 'incomplete'}."
                )
                if missing_approvals:
                    runtime_text += f" Missing approval boundary: {missing_approvals[0]}."
            browser_governance = runtime_policy.get("browserDomainGovernance") if isinstance(runtime_policy.get("browserDomainGovernance"), dict) else {}
            if browser_governance:
                uncovered_domains = browser_governance.get("uncoveredDomains") if isinstance(browser_governance.get("uncoveredDomains"), list) else []
                runtime_text += (
                    f" Browser domain governance: {len(browser_governance.get('coveredDomains') or [])}/"
                    f"{len(browser_governance.get('observedDomains') or [])} observed domain(s) covered, "
                    f"{len(browser_governance.get('allowedDomains') or [])} allowed."
                )
                if uncovered_domains:
                    runtime_text += f" First uncovered browser domain: {uncovered_domains[0]}."
            session_contracts = runtime.get("sessionContracts") if isinstance(runtime.get("sessionContracts"), dict) else {}
            if session_contracts:
                runtime_text += (
                    f" Runtime cost: {session_contracts.get('creditsSpent', 0)} credits, "
                    f"{session_contracts.get('durationSeconds', 0)}s duration."
                )
            timeline = session_contracts.get("timeline") if isinstance(session_contracts.get("timeline"), dict) else {}
            if timeline:
                runtime_text += (
                    f" Runtime timeline: {timeline.get('steps', 0)} steps, "
                    f"{timeline.get('toolSteps', 0)} tool, {timeline.get('skillSteps', 0)} skill, "
                    f"{timeline.get('replayReadySessions', 0)} replay-ready sessions."
                )
            artifact_outputs = runtime.get("artifactOutputs") if isinstance(runtime.get("artifactOutputs"), dict) else {}
            if artifact_outputs:
                runtime_text += (
                    f" Artifact outputs: {artifact_outputs.get('total', 0)} business output(s), "
                    f"{artifact_outputs.get('runtimeLinked', 0)} runtime-linked, "
                    f"{artifact_outputs.get('reviewRequired', 0)} pending review."
                )
                if int(artifact_outputs.get("blockedForReuse") or 0):
                    runtime_text += f" Artifact reuse blocked: {artifact_outputs.get('blockedForReuse', 0)}."
        work_text = ""
        if sla:
            work_text = f" Work attention items: {sla.get('needsAttention', 0)}."
            triggers = work_orchestration.get("triggers") if isinstance(work_orchestration.get("triggers"), dict) else {}
            budgets = work_orchestration.get("budgets") if isinstance(work_orchestration.get("budgets"), dict) else {}
            retries = work_orchestration.get("retries") if isinstance(work_orchestration.get("retries"), dict) else {}
            if triggers or budgets or retries:
                work_text += (
                    f" Work operations: {triggers.get('due', 0)} due trigger(s), "
                    f"{budgets.get('exhaustedItems', 0)} budget-exhausted item(s), "
                    f"{retries.get('totalRetryCount', 0)} retry attempt(s)."
                )
            contracts = work_orchestration.get("contracts") if isinstance(work_orchestration.get("contracts"), dict) else {}
            if contracts:
                work_text += (
                    f" Work contracts: {contracts.get('withContract', 0)}/{contracts.get('total', 0)} normalized, "
                    f"{contracts.get('slaTracked', 0)} SLA-tracked, {contracts.get('auditTrails', 0)} with audit trails."
                )
                work_text += (
                    f" Automation gate: {contracts.get('unattendedReady', 0)} unattended-ready, "
                    f"{contracts.get('unattendedBlocked', 0)} blocked."
                )
                work_gate = contracts.get("workOperationsGate") if isinstance(contracts.get("workOperationsGate"), dict) else {}
                if work_gate:
                    work_text += f" Work operations gate: {work_gate.get('state', 'unknown')}."
                blockers = contracts.get("automationBlockers") if isinstance(contracts.get("automationBlockers"), list) else []
                if blockers:
                    first_blocker = blockers[0] if isinstance(blockers[0], dict) else {}
                    work_text += f" First automation blocker: {first_blocker.get('name') or 'unknown'}."
        next_action = guidance.get("primaryNextAction") if isinstance(guidance.get("primaryNextAction"), dict) else next_actions[0] if next_actions and isinstance(next_actions[0], dict) else {}
        risks = guidance.get("riskAlerts") if isinstance(guidance.get("riskAlerts"), list) else []
        risk_text = f" Automata sees {len(risks)} risk alert(s)." if risks else ""
        next_text = f" Next: {next_action.get('action')}" if next_action.get("action") else " Tell me what you want to inspect or configure next."
        return (
            f"I can see {counts.get('companies', 0)} company, {counts.get('agents', 0)} agent config(s), "
            f"{counts.get('connectors', 0)} connector(s), {counts.get('tools', 0)} tool(s), "
            f"and {counts.get('skills', 0)} skill(s) in your scoped Studio workspace."
            f"{score_text}{studio_os_text}{company_setup_text}{factory_text}{coverage_text}{resource_text}{runtime_text}{work_text}{risk_text}{next_text}"
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
