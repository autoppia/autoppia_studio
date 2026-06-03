from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class ConnectorExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectorConfig:
    connector_id: str
    company_id: str
    email: str
    name: str
    type: str
    status: str
    config: dict[str, Any]

    def get(self, *names: str, default: str = "") -> str:
        for name in names:
            value = self.config.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return default

    def require(self, *names: str) -> str:
        value = self.get(*names)
        if not value:
            joined = " or ".join(names)
            raise ConnectorExecutionError(f"{self.name} is missing required config: {joined}")
        return value


@dataclass(frozen=True)
class ConnectorToolResult:
    tool: str
    connectorId: str
    connectorName: str
    success: bool
    output: Any = None
    error: str = ""

    def model_dump(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "connectorId": self.connectorId,
            "connectorName": self.connectorName,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


class BaseConnector:
    type = "api"

    def __init__(self, config: ConnectorConfig):
        self.config = config

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ConnectorToolResult:
        raise ConnectorExecutionError(f"{self.config.type} connector does not implement {tool_name}")

    def result(self, tool_name: str, output: Any = None) -> ConnectorToolResult:
        return ConnectorToolResult(
            tool=tool_name,
            connectorId=self.config.connector_id,
            connectorName=self.config.name,
            success=True,
            output=output,
        )


class HttpApiConnector(BaseConnector):
    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(method, url, **kwargs)
            if response.status_code >= 400:
                raise ConnectorExecutionError(f"{self.config.name} API returned {response.status_code}: {response.text[:300]}")
            try:
                return response.json()
            except ValueError:
                return response.text


def read_text_file(path: str, limit: int = 8000) -> str:
    raw = Path(path)
    if not raw.exists() or not raw.is_file():
        return ""
    try:
        return raw.read_text(errors="ignore")[:limit]
    except Exception:
        return ""
