from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.services.vectorstore.base import VectorChunk, VectorHit


class ChromaVectorStore:
    def __init__(self, persist_directory: str | None = None):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("chromadb is not installed. Install it or set AUTOMATA_VECTORSTORE=local.") from exc

        directory = persist_directory or os.getenv("AUTOMATA_CHROMA_DIR") or str(Path.home() / ".automata" / "chroma")
        self.client = chromadb.PersistentClient(path=directory)

    def _collection(self, name: str):
        return self.client.get_or_create_collection(name=name)

    async def upsert(self, collection: str, chunks: list[VectorChunk]) -> None:
        if not chunks:
            return
        target = self._collection(collection)
        target.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=[chunk.embedding for chunk in chunks],
            metadatas=[{"documentId": chunk.document_id, **chunk.metadata} for chunk in chunks],
        )

    async def query(self, collection: str, embedding: list[float], k: int = 5, filters: dict[str, Any] | None = None) -> list[VectorHit]:
        target = self._collection(collection)
        result = target.query(query_embeddings=[embedding], n_results=max(1, int(k or 5)), where=filters or None)
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits = []
        for idx, chunk_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
            distance = float(distances[idx]) if idx < len(distances) else 1.0
            hits.append(
                VectorHit(
                    id=str(chunk_id),
                    document_id=str(metadata.get("documentId") or ""),
                    text=str(docs[idx] if idx < len(docs) else ""),
                    score=1.0 - distance,
                    metadata=metadata,
                )
            )
        return hits

    async def delete(self, collection: str, document_id: str) -> None:
        target = self._collection(collection)
        target.delete(where={"documentId": document_id})
