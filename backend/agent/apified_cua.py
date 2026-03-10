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
        """Call the autoppia_operator /act endpoint.

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
        }
        if history is not None:
            payload["history"] = history
        if state_in:
            payload["state_in"] = state_in

        last_error = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for path in ("/act", "/step"):
                try:
                    response = await client.post(f"{self.base_url}{path}", json=payload)
                    response.raise_for_status()
                    return response.json()
                except Exception as e:
                    logger.warning(f"Request to {path} failed ({type(e).__name__}): {e}")
                    last_error = e
                    continue

        raise ConnectionError(f"CUA agent unreachable: {last_error}")
