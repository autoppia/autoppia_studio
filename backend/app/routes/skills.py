import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import skills_collection

router = APIRouter()
logger = logging.getLogger(__name__)


class SkillParameter(BaseModel):
    name: str
    description: str
    defaultValue: str = ""


class SkillCreateRequest(BaseModel):
    email: str
    name: str
    goal: str = ""
    instructions: str = ""
    parameters: List[SkillParameter] = []
    actions: List[Any] = []


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
            skills.append({
                "skillId": doc.get("skillId", ""),
                "name": doc.get("name", ""),
                "goal": doc.get("goal", ""),
                "instructions": doc.get("instructions", ""),
                "parameters": doc.get("parameters", []),
                "actions": doc.get("actions", []),
                "createdAt": doc.get("createdAt"),
            })
        return {"skills": skills}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills")
async def create_skill(body: SkillCreateRequest):
    """Create a new skill."""
    try:
        now = datetime.now(timezone.utc)
        skill_id = str(uuid.uuid4())
        doc = {
            "skillId": skill_id,
            "email": body.email,
            "name": body.name,
            "goal": body.goal,
            "instructions": body.instructions,
            "parameters": [p.model_dump() for p in body.parameters],
            "actions": body.actions,
            "createdAt": now,
        }
        await skills_collection.insert_one(doc)
        return {"success": True, "skillId": skill_id}
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
        result = await skills_collection.update_one(
            {"skillId": skill_id},
            {"$set": {
                "name": body.name,
                "goal": body.goal,
                "instructions": body.instructions,
                "parameters": [p.model_dump() for p in body.parameters],
                "actions": body.actions,
            }},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"success": True}
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
        simplified = {k: v for k, v in args.items()
                      if k in ("url", "text", "query", "keys", "direction", "script")}
        action_summary.append({"action": name, "args": simplified})

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning basic skill structure")
        return _basic_skill_structure(
            prompt, initial_url, skill_name, skill_goal, skill_instructions, action_summary
        )

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
        return _basic_skill_structure(
            prompt, initial_url, skill_name, skill_goal, skill_instructions, action_summary
        )


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
        "instructions": prompt,              # instructions = the actual prompt
        "parameters": [],
        "actions": action_summary,
    }
