import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import skills_collection
from app.services.runtime_policy import serialize_runtime_policy
from app.services.skill_evidence import skill_hardening_status
from app.services.skill_lifecycle import append_skill_version_event
from app.services.skill_lifecycle import skill_promotion_status
from app.services.skill_lifecycle import skill_version
from app.services.skill_lifecycle import skill_version_history
from app.services.skill_manifests import skill_package_manifest

router = APIRouter()
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _legacy_skill_lineage(doc: dict[str, Any]) -> dict[str, Any]:
    actions = doc.get("actions") if isinstance(doc.get("actions"), list) else []
    tool_ids = []
    for action in actions:
        if isinstance(action, dict):
            tool_ids.append(action.get("action") or action.get("name") or "")
    return {
        "trajectoryIds": _dedupe(doc.get("trajectoryIds") or []),
        "benchmarkIds": _dedupe(doc.get("benchmarkIds") or []),
        "evalIds": _dedupe(doc.get("evalIds") or []),
        "connectorIds": _dedupe(doc.get("connectorIds") or []),
        "toolIds": _dedupe(tool_ids),
        "sources": _dedupe([doc.get("source") or "legacy_skills_api"]),
        "recordedActions": len(actions),
    }


def _legacy_hardening_doc(doc: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    return {
        **doc,
        "whenToUse": doc.get("whenToUse") or doc.get("goal") or "",
        "trajectoryIds": doc.get("trajectoryIds") or (["legacy_action_recording"] if lineage.get("recordedActions") else []),
    }


def _legacy_manifest_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        **doc,
        "capabilityId": doc.get("capabilityId") or doc.get("skillId") or "",
        "description": doc.get("description") or doc.get("goal") or "",
        "whenToUse": doc.get("whenToUse") or doc.get("goal") or "",
    }


def _packaged_skill_doc(base: dict[str, Any], *, previous: dict[str, Any] | None = None, reason: str = "legacy_skill_saved") -> dict[str, Any]:
    now = _now()
    doc = {**(previous or {}), **base}
    version = skill_version({**(previous or {}), **doc})
    promotion_status = skill_promotion_status(doc)
    doc.update(
        {
            "capabilityKind": "skill",
            "skillId": doc.get("skillId", ""),
            "status": promotion_status,
            "promotionStatus": promotion_status,
            "version": version,
            "versionLabel": doc.get("versionLabel") or f"v{version}",
            "riskPolicy": doc.get("riskPolicy") or "human_approval_for_writes",
            "source": doc.get("source") or "legacy_skills_api",
            "updatedAt": now,
        }
    )
    doc.setdefault("createdAt", now)
    lineage = _legacy_skill_lineage(doc)
    hardening = skill_hardening_status(_legacy_hardening_doc(doc, lineage), trajectory_docs=[], latest_regression=None)
    if reason:
        doc["versionHistory"] = append_skill_version_event(previous or {}, doc, now=now, reason=reason)
    else:
        doc["versionHistory"] = skill_version_history(doc, version=version, promotion_status=promotion_status)
    doc["lineage"] = lineage
    doc["hardeningStatus"] = hardening
    doc["skillPackage"] = skill_package_manifest(
        _legacy_manifest_doc(doc),
        version=version,
        promotion_status=promotion_status,
        runtime_policy=serialize_runtime_policy(doc),
        lineage=lineage,
        hardening=hardening,
        latest_regression=None,
        source_trajectories=[],
        regression_cases=[],
        version_history=doc["versionHistory"],
    )
    return doc


def _serialize_skill(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "skillId": doc.get("skillId", ""),
        "capabilityKind": doc.get("capabilityKind", "skill"),
        "name": doc.get("name", ""),
        "goal": doc.get("goal", ""),
        "instructions": doc.get("instructions", ""),
        "parameters": doc.get("parameters", []),
        "actions": doc.get("actions", []),
        "status": doc.get("status", "draft"),
        "promotionStatus": doc.get("promotionStatus", "draft"),
        "version": doc.get("version", 1),
        "versionLabel": doc.get("versionLabel", "v1"),
        "versionHistory": doc.get("versionHistory", []),
        "lineage": doc.get("lineage", {}),
        "hardeningStatus": doc.get("hardeningStatus", {}),
        "skillPackage": doc.get("skillPackage", {}),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


class SkillParameter(BaseModel):
    name: str
    description: str
    defaultValue: str = ""


class SkillCreateRequest(BaseModel):
    email: str
    name: str
    goal: str = ""
    instructions: str = ""
    parameters: List[SkillParameter] = Field(default_factory=list)
    actions: List[Any] = Field(default_factory=list)


class SkillParameterizeRequest(BaseModel):
    action_history: List[Any]
    prompt: str
    initial_url: str = ""
    skill_name: str = ""
    skill_goal: str = ""
    skill_instructions: str = ""


@router.get("/skills")
async def get_skills(email: str):
    """List all skills for a user."""
    try:
        cursor = skills_collection.find({"email": email}).sort("createdAt", -1)
        skills = []
        async for doc in cursor:
            skills.append(_serialize_skill(_packaged_skill_doc(doc, previous=doc, reason="")))
        return {"skills": skills}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills")
async def create_skill(body: SkillCreateRequest):
    """Create a new skill."""
    try:
        skill_id = str(uuid.uuid4())
        doc = _packaged_skill_doc({
            "skillId": skill_id,
            "email": body.email,
            "name": body.name,
            "goal": body.goal,
            "instructions": body.instructions,
            "parameters": [p.model_dump() for p in body.parameters],
            "actions": body.actions,
            "status": "draft",
            "promotionStatus": "draft",
        })
        await skills_collection.insert_one(doc)
        return {"success": True, "skillId": skill_id, "skill": _serialize_skill(doc)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills/parameterize")
async def parameterize_skill(body: SkillParameterizeRequest):
    """Use LLM to analyze action history and return a parameterized skill definition."""
    try:
        result = await _parameterize_with_llm(
            action_history=body.action_history,
            prompt=body.prompt,
            initial_url=body.initial_url,
            skill_name=body.skill_name,
            skill_goal=body.skill_goal,
            skill_instructions=body.skill_instructions,
        )
        return result
    except Exception as e:
        logger.error(f"Parameterize error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, body: SkillCreateRequest):
    """Update an existing skill."""
    try:
        existing = await skills_collection.find_one({"skillId": skill_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Skill not found")
        doc = _packaged_skill_doc(
            {
                "skillId": skill_id,
                "email": body.email or existing.get("email", ""),
                "name": body.name,
                "goal": body.goal,
                "instructions": body.instructions,
                "parameters": [p.model_dump() for p in body.parameters],
                "actions": body.actions,
            },
            previous=existing,
            reason="legacy_skill_updated",
        )
        result = await skills_collection.update_one(
            {"skillId": skill_id},
            {"$set": doc},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"success": True, "skill": _serialize_skill(doc)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """Delete a skill by ID."""
    try:
        result = await skills_collection.delete_one({"skillId": skill_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _parameterize_with_llm(
    action_history: list,
    prompt: str,
    initial_url: str,
    skill_name: str,
    skill_goal: str,
    skill_instructions: str,
) -> dict:
    """Call Claude to parameterize the action history into a reusable skill."""
    # Build compact action list for the LLM (strip selectors noise, keep key fields)
    action_summary = []
    for entry in action_history:
        tc = entry.get("tool_call", {})
        name = tc.get("name", "")
        args = tc.get("arguments", {})
        # Skip no-op and screenshot actions
        if name in ("browser.screenshot", "browser.wait", "browser.done"):
            continue
        # Simplify args: only keep meaningful keys
        simplified = {k: v for k, v in args.items() if k in ("url", "text", "query", "keys", "direction", "script")}
        action_summary.append({"action": name, "args": simplified})

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning basic skill structure")
        return _basic_skill_structure(prompt, initial_url, skill_name, skill_goal, skill_instructions, action_summary)

    try:
        import anthropic

        system_prompt = (
            "You are an expert at converting browser automation recordings into reusable, "
            "parameterized skill definitions.\n\n"
            "Key concept:\n"
            "- The 'prompt' is the ACTUAL instruction sent to the agent (what it executes)\n"
            "- The 'goal' is just a human-readable description/label for the skill\n"
            "- 'instructions' in the output = the parameterized version of the prompt\n\n"
            "Your job:\n"
            "1. Take the original prompt and replace hardcoded values with {{parameter_name}} placeholders\n"
            "2. Identify variable parts: URLs, search terms, usernames, passwords, form values, dates, etc.\n"
            "3. Build a parameters list with name, description, and defaultValue for each\n"
            "4. Also parameterize the action history the same way\n\n"
            "Return ONLY valid JSON (no markdown, no extra text):\n"
            "{\n"
            '  "name": "Short descriptive skill name",\n'
            '  "goal": "One-line human description of what the skill does (no placeholders needed)",\n'
            '  "instructions": "Parameterized version of the original prompt with {{placeholders}}",\n'
            '  "parameters": [\n'
            '    {"name": "param_name", "description": "What this param is", "defaultValue": "original value"}\n'
            "  ],\n"
            '  "actions": [\n'
            '    {"action": "browser.navigate", "args": {"url": "{{target_url}}"}}\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Parameter names must be snake_case\n"
            "- Passwords/secrets: set defaultValue to empty string\n"
            "- Fixed infrastructure URLs (google.com) should NOT be parameterized\n"
            "- If skill_goal is provided, use it as the 'goal' field (it's the user's label)\n"
            "- Keep actions list concise — only the core steps"
        )

        lines = [
            f"Original prompt (actual agent instruction to parameterize): {prompt}",
            f"Starting URL: {initial_url or '(none)'}",
        ]
        if skill_name:
            lines.append(f"Skill name hint: {skill_name}")
        if skill_goal:
            lines.append(f"Skill description/goal (use this as the 'goal' field): {skill_goal}")
        lines.append("")
        lines.append("Action history (what the agent actually did):")
        lines.append(json.dumps(action_summary, indent=2))
        lines.append("")
        lines.append("Produce the parameterized skill JSON.")

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )

        response_text = message.content[0].text.strip()

        # Strip markdown fences if present
        if "```" in response_text:
            parts = response_text.split("```")
            for part in parts:
                stripped = part.lstrip("json").strip()
                if stripped.startswith("{"):
                    response_text = stripped
                    break

        return json.loads(response_text)

    except Exception as e:
        logger.error(f"LLM parameterization failed: {e}", exc_info=True)
        return _basic_skill_structure(prompt, initial_url, skill_name, skill_goal, skill_instructions, action_summary)


def _basic_skill_structure(
    prompt: str,
    initial_url: str,
    skill_name: str,
    skill_goal: str,
    skill_instructions: str,
    action_summary: list,
) -> dict:
    """Fallback when LLM is unavailable — return unparameterized structure."""
    return {
        "name": skill_name or prompt[:60],
        "goal": skill_goal or prompt[:100],  # goal is the label/description
        "instructions": prompt,  # instructions = the actual prompt
        "parameters": [],
        "actions": action_summary,
    }
