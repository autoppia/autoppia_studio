from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import assistant_conversations_collection, assistant_memories_collection

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - optional local dependency.
    AsyncOpenAI = None  # type: ignore[assignment]


SECRET_RE = re.compile(r"(secret|token|password|api[_-]?key|refresh|credential|bearer\s+[a-z0-9._-]+)", re.IGNORECASE)
MAX_CONVERSATION_CHARS = 10000
MAX_MEMORY_CHARS = 3500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(text: str) -> str:
    redacted_lines: list[str] = []
    for line in str(text or "").splitlines():
        if SECRET_RE.search(line):
            redacted_lines.append("[redacted secret-like content]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def _conversation_title(doc: dict[str, Any]) -> str:
    messages = [item for item in doc.get("messages", []) if isinstance(item, dict)]
    for message in reversed(messages):
        if message.get("role") == "user" and str(message.get("content") or "").strip():
            return str(message.get("content") or "").strip()[:120]
    return str(doc.get("conversationId") or "Conversation")


def _conversation_text(doc: dict[str, Any]) -> str:
    lines: list[str] = []
    for message in [item for item in doc.get("messages", []) if isinstance(item, dict)][-60:]:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content[:1200]}")
    return _redact("\n".join(lines))[:MAX_CONVERSATION_CHARS]


def _fallback_conversation_summary(doc: dict[str, Any]) -> str:
    text = _conversation_text(doc)
    if not text:
        return f"No useful user/assistant messages found. Title: {_conversation_title(doc)}"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    user_lines = [line.replace("user:", "User:", 1) for line in lines if line.startswith("user:")][-5:]
    assistant_lines = [line.replace("assistant:", "Assistant:", 1) for line in lines if line.startswith("assistant:")][-3:]
    summary_lines = [f"Title: {_conversation_title(doc)}"]
    summary_lines.extend(user_lines)
    summary_lines.extend(assistant_lines)
    return "\n".join(summary_lines)[:1800]


async def _llm_summarize_conversation(doc: dict[str, Any]) -> str:
    if AsyncOpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return _fallback_conversation_summary(doc)
    text = _conversation_text(doc)
    if not text:
        return _fallback_conversation_summary(doc)
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.responses.create(
        model=os.getenv("AUTOMATA_ASSISTANT_MEMORY_MODEL", "gpt-5-mini"),
        instructions=(
            "Summarize this Automata Studio conversation as durable product memory. "
            "Keep user preferences, decisions, created/changed resources, important ids/names, unresolved issues, and next actions. "
            "Do not include raw secrets, tokens, API keys, passwords, or long transcripts. Be concise."
        ),
        input=f"Conversation title: {_conversation_title(doc)}\n\n{text}",
        reasoning={"effort": "minimal"},
        text={"verbosity": "low"},
        max_output_tokens=500,
    )
    summary = _redact(str(getattr(response, "output_text", "") or "").strip())
    return summary[:1800] if summary else _fallback_conversation_summary(doc)


async def _llm_merge_summaries(summaries: list[str]) -> str:
    joined = _redact("\n\n---\n\n".join(summaries))[:18000]
    if not joined:
        return ""
    if AsyncOpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return joined[:MAX_MEMORY_CHARS]
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.responses.create(
        model=os.getenv("AUTOMATA_ASSISTANT_MEMORY_MODEL", "gpt-5-mini"),
        instructions=(
            "Merge conversation summaries into compact long-term memory for Automata Studio. "
            "Prefer facts useful for future assistance: user identity/preferences, active company, configured resources, pending work, known issues, and product feedback. "
            "Remove duplicates and omit secrets."
        ),
        input=joined,
        reasoning={"effort": "minimal"},
        text={"verbosity": "low"},
        max_output_tokens=900,
    )
    merged = _redact(str(getattr(response, "output_text", "") or "").strip())
    return merged[:MAX_MEMORY_CHARS] if merged else joined[:MAX_MEMORY_CHARS]


async def get_assistant_memory(email: str, company_id: str = "") -> dict[str, Any] | None:
    query = {"email": email, "companyId": company_id or ""}
    return await assistant_memories_collection.find_one(query, {"_id": 0})


async def rebuild_assistant_memory(email: str, company_id: str = "", *, limit: int = 200) -> dict[str, Any]:
    query: dict[str, Any] = {"email": email}
    if company_id:
        query["companyId"] = company_id
    cursor = assistant_conversations_collection.find(query, {"_id": 0}).sort("updatedAt", -1).limit(max(1, min(limit, 500)))
    docs = await cursor.to_list(length=max(1, min(limit, 500)))
    now = _now_iso()
    summaries: list[str] = []
    for doc in docs:
        summary = await _llm_summarize_conversation(doc)
        if not summary:
            continue
        summaries.append(
            f"{_conversation_title(doc)} ({doc.get('updatedAt') or doc.get('createdAt') or ''})\n{summary}"
        )
        conversation_id = str(doc.get("conversationId") or "")
        if conversation_id:
            await assistant_conversations_collection.update_one(
                {"email": email, "conversationId": conversation_id},
                {"$set": {"memorySummary": summary, "memorySummaryUpdatedAt": now}},
            )
    merged = await _llm_merge_summaries(summaries)
    memory_id = f"{email}:{company_id or 'global'}"
    memory_doc = {
        "memoryId": memory_id,
        "email": email,
        "companyId": company_id or "",
        "summary": merged,
        "conversationCount": len(docs),
        "summarizedConversationCount": len(summaries),
        "model": os.getenv("AUTOMATA_ASSISTANT_MEMORY_MODEL", "gpt-5-mini") if os.getenv("OPENAI_API_KEY") else "fallback",
        "updatedAt": now,
    }
    await assistant_memories_collection.update_one(
        {"memoryId": memory_id},
        {
            "$set": memory_doc,
            "$setOnInsert": {"createdAt": now, "internalId": str(uuid.uuid4())},
        },
        upsert=True,
    )
    return memory_doc
