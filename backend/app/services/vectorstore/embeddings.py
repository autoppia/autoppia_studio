from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol


class EmbeddingModel(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashEmbeddingModel:
    def __init__(self, dimensions: int = 256):
        self.dimensions = max(32, int(dimensions or 256))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-zA-Z0-9_áéíóúñÁÉÍÓÚÑ]{2,}", (text or "").lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAIEmbeddingModel:
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.embeddings.create(model=self.model, input=texts)
        return [list(item.embedding) for item in response.data]


def get_embedding_model() -> EmbeddingModel:
    provider = os.getenv("AUTOMATA_EMBEDDINGS", "hash").strip().lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return OpenAIEmbeddingModel(os.getenv("AUTOMATA_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))
    return HashEmbeddingModel(int(os.getenv("AUTOMATA_HASH_EMBEDDING_DIMENSIONS", "256")))
