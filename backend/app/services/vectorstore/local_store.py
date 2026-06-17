from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from app.services.vectorstore.base import VectorChunk, VectorHit


LOCAL_VECTORSTORE_DIR = Path(os.getenv("AUTOMATA_LOCAL_VECTORSTORE_DIR", Path.home() / ".automata" / "vectorstore"))


def _safe_collection(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value or "default"))[:120] or "default"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(length))
    norm_a = math.sqrt(sum(value * value for value in a[:length]))
    norm_b = math.sqrt(sum(value * value for value in b[:length]))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


class LocalJsonVectorStore:
    def __init__(self, root: Path | None = None):
        self.root = root or LOCAL_VECTORSTORE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, collection: str) -> Path:
        return self.root / f"{_safe_collection(collection)}.jsonl"

    async def upsert(self, collection: str, chunks: list[VectorChunk]) -> None:
        path = self._path(collection)
        existing = self._read(path)
        incoming_ids = {chunk.id for chunk in chunks}
        rows = [row for row in existing if row.get("id") not in incoming_ids]
        rows.extend(
            {
                "id": chunk.id,
                "documentId": chunk.document_id,
                "text": chunk.text,
                "embedding": chunk.embedding,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        )
        self._write(path, rows)

    async def query(self, collection: str, embedding: list[float], k: int = 5, filters: dict[str, Any] | None = None) -> list[VectorHit]:
        rows = self._read(self._path(collection))
        filters = filters or {}
        hits = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if any(metadata.get(key) != value for key, value in filters.items()):
                continue
            hits.append(
                VectorHit(
                    id=str(row.get("id") or ""),
                    document_id=str(row.get("documentId") or ""),
                    text=str(row.get("text") or ""),
                    score=_cosine(embedding, row.get("embedding") if isinstance(row.get("embedding"), list) else []),
                    metadata=metadata,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: max(1, int(k or 5))]

    async def delete(self, collection: str, document_id: str) -> None:
        path = self._path(collection)
        rows = [row for row in self._read(path) if row.get("documentId") != document_id]
        self._write(path, rows)

    def _read(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _write(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
