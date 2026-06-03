from __future__ import annotations

import json
import os
from typing import Any


def _compact_run(run: dict[str, Any], eval_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": eval_doc.get("prompt", ""),
        "successCriteria": eval_doc.get("successCriteria", ""),
        "initialUrl": eval_doc.get("initialUrl", ""),
        "actions": run.get("actions", [])[-50:],
        "screenshots": run.get("screenshots", [])[-3:],
    }


async def judge_eval_run(*, run: dict[str, Any], eval_doc: dict[str, Any], user_context: dict[str, Any] | None = None) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "label": "pending",
            "confidence": 0.0,
            "needsHumanReview": True,
            "reasoning": "OPENAI_API_KEY is not configured, so LLMJudge could not run.",
            "judge": "llm_judge_unavailable",
        }

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    model = os.getenv("AUTOMATA_EVAL_JUDGE_MODEL", "gpt-5-mini")
    payload = _compact_run(run, eval_doc)
    prompt = (
        "You are Automata LLMJudge. Decide whether the agent run satisfies the task. "
        "Use the success criteria, actions, screenshots if present, and user context. "
        "Return strict JSON with label pass|fail|pending, confidence 0-1, needsHumanReview boolean, reasoning string.\n\n"
        f"Run:\n{json.dumps(payload, ensure_ascii=False)[:12000]}\n\n"
        f"User context:\n{json.dumps(user_context or {}, ensure_ascii=False)[:4000]}"
    )
    response = await client.responses.create(
        model=model,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    raw = response.output_text
    try:
        data = json.loads(raw)
    except Exception:
        data = {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": raw[:1000]}
    label = str(data.get("label") or "pending").lower()
    if label not in {"pass", "fail", "pending"}:
        label = "pending"
    confidence = float(data.get("confidence") or 0)
    return {
        "label": label,
        "confidence": max(0.0, min(1.0, confidence)),
        "needsHumanReview": bool(data.get("needsHumanReview", confidence < 0.75 or label == "pending")),
        "reasoning": str(data.get("reasoning") or ""),
        "judge": model,
    }
