import logging
import httpx
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ApifiedCUA:
    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    async def health_check(self) -> bool:
        """Return True if the CUA agent is reachable."""
        async with httpx.AsyncClient(timeout=10) as client:
            for path in ("/health", "/"):
                try:
                    response = await client.get(f"{self.base_url}{path}")
                    if response.status_code < 500:
                        return True
                except Exception:
                    continue
        return False

    async def act(
        self,
        task_id: str,
        prompt: str,
        snapshot_html: str,
        url: str,
        step_index: int,
        history: Optional[List[Dict[str, Any]]] = None,
        state_in: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call the agent runtime /step endpoint.

        Returns the full response dict with tool_calls, done, content,
        reasoning, state_out, etc.
        """
        payload: Dict[str, Any] = {
            "task_id": task_id,
            "prompt": prompt,
            "snapshot_html": snapshot_html,
            "url": url,
            "step_index": int(step_index),
            "include_reasoning": True,
            "runtime_tools": [
                {
                    "name": "artifacts.create",
                    "description": "Create a renderable artifact in the current session. Use for reports, markdown docs, HTML, SVG, Mermaid, CSV/JSON, code, and other deliverables that should be shown to the user in the session UI.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "artifactType": {
                                "type": "string",
                                "description": "markdown, html, react, svg, mermaid, csv, json, javascript, typescript, python, or text",
                            },
                            "content": {"type": "string"},
                            "fileName": {"type": "string"},
                            "metadata": {"type": "object"},
                        },
                        "required": ["title", "artifactType", "content"],
                    },
                }
            ],
        }
        if history is not None:
            payload["history"] = history
        if state_in:
            payload["state_in"] = state_in

        last_error = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(f"{self.base_url}/step", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"Request to /step failed ({type(e).__name__}): {e}")
                last_error = e

        raise ConnectionError(f"CUA agent unreachable: {last_error}")
