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
    ) -> Optional[List[Dict[str, Any]]]:
        """Call the autoppia_operator /act endpoint.

        Returns:
            list[dict] — raw action dicts to execute
            None — the CUA signalled the task is done (API returned empty actions)
        """
        payload: Dict[str, Any] = {
            "task_id": task_id,
            "prompt": prompt,
            "snapshot_html": snapshot_html,
            "url": url,
            "step_index": int(step_index),
        }
        if history is not None:
            payload["history"] = history

        last_error = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for path in ("/act", "/step"):
                try:
                    response = await client.post(f"{self.base_url}{path}", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    actions_data = data.get("actions", [])

                    # API returned empty actions = task done
                    if not actions_data:
                        return None

                    return actions_data
                except Exception as e:
                    logger.warning(f"Request to {path} failed ({type(e).__name__}): {e}")
                    last_error = e
                    continue

        # All endpoints failed — raise so the caller knows it's an error,
        # not a "task done" signal.
        raise ConnectionError(f"CUA agent unreachable: {last_error}")
