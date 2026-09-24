"""Embedding provider (Gemini first; bake-off may swap it). Cached by (model, text, day)."""

import math
from typing import Protocol

import httpx

from seo_engine.config import ModelSettings, Secrets
from seo_engine.providers.base import CostSink, DailyCache, no_cost, request_with_retry

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/"
BATCH_LIMIT = 100


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity; inputs from `embed` are already unit length."""
    return sum(x * y for x, y in zip(a, b, strict=True))


class GeminiEmbeddings:
    def __init__(
        self,
        models: ModelSettings,
        api_key: str,
        cache: DailyCache,
        cost_sink: CostSink = no_cost,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        self.models = models
        self.cache = cache
        self.cost_sink = cost_sink
        self.http = client or httpx.Client(
            base_url=GEMINI_URL, headers={"x-goog-api-key": api_key}, timeout=60.0
        )

    @classmethod
    def from_env(
        cls, models: ModelSettings, cache: DailyCache, cost_sink: CostSink = no_cost
    ) -> "GeminiEmbeddings":
        return cls(models, Secrets().gemini_api_key.get_secret_value(), cache, cost_sink)

    def _key(self, text: str) -> list[str | int]:
        return [self.models.embedding, self.models.embedding_dims, text]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: dict[str, list[float]] = {}
        missing: list[str] = []
        for text in dict.fromkeys(texts):
            hit = self.cache.get("embed", self._key(text))
            if hit is None:
                missing.append(text)
            else:
                out[text] = hit
        for start in range(0, len(missing), BATCH_LIMIT):
            batch = missing[start : start + BATCH_LIMIT]
            for text, vec in zip(batch, self._call(batch), strict=True):
                out[text] = vec
                self.cache.set("embed", self._key(text), vec)
        return [out[t] for t in texts]

    def _call(self, batch: list[str]) -> list[list[float]]:
        model = f"models/{self.models.embedding}"
        body = {
            "requests": [
                {
                    "model": model,
                    "content": {"parts": [{"text": t}]},
                    "taskType": "SEMANTIC_SIMILARITY",
                    "outputDimensionality": self.models.embedding_dims,
                }
                for t in batch
            ]
        }
        resp = request_with_retry(self.http, "POST", f"{model}:batchEmbedContents", json=body)
        vectors = [normalise(e["values"]) for e in resp.json()["embeddings"]]
        approx_tokens = sum(len(t) for t in batch) / 4
        self.cost_sink(
            approx_tokens * self.models.embedding_price_per_m / 1_000_000,
            f"gemini.{self.models.embedding}",
        )
        return vectors
