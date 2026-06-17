from __future__ import annotations

import os

from app.services.vectorstore.base import VectorStore
from app.services.vectorstore.local_store import LocalJsonVectorStore


def get_vectorstore() -> VectorStore:
    provider = os.getenv("AUTOMATA_VECTORSTORE", "local").strip().lower()
    if provider == "chroma":
        from app.services.vectorstore.chroma_store import ChromaVectorStore

        return ChromaVectorStore()
    if provider in {"local", "json", "jsonl"}:
        return LocalJsonVectorStore()
    raise RuntimeError(f"Unsupported vectorstore provider: {provider}")
