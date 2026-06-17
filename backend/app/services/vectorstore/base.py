from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class VectorChunk:
    id: str
    document_id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorHit:
    id: str
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    async def upsert(self, collection: str, chunks: list[VectorChunk]) -> None:
        ...

    async def query(self, collection: str, embedding: list[float], k: int = 5, filters: dict[str, Any] | None = None) -> list[VectorHit]:
        ...

    async def delete(self, collection: str, document_id: str) -> None:
        ...
