"""LLM provider. Every call returns a Pydantic-validated object (CLAUDE.md rule 2).

LLMs only name topics, classify, judge and write text; they never count (rule 1).
"""

import json
from typing import Any, Literal, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from seo_engine.config import ModelSettings, Secrets
from seo_engine.providers.base import CostSink, no_cost, request_with_retry

Tier = Literal["judgment", "bulk", "checker"]
T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    """The model returned invalid output twice."""


class LLMProvider(Protocol):
    def structured(self, system: str, user: str, schema: type[T], tier: Tier = "bulk") -> T: ...


def schema_instructions(schema: type[BaseModel]) -> str:
    return (
        "Reply with a single JSON object and nothing else. It must validate against this "
        f"JSON schema:\n{json.dumps(schema.model_json_schema(), separators=(',', ':'))}"
    )


class DeepSeekLLM:
    """DeepSeek chat completions (OpenAI-compatible) in JSON mode."""

    def __init__(
        self,
        models: ModelSettings,
        api_key: str,
        cost_sink: CostSink = no_cost,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise LLMOutputError("DEEPSEEK_API_KEY is not set in .env")
        self.models = models
        self.cost_sink = cost_sink
        self.http = client or httpx.Client(
            base_url=models.deepseek_base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(180.0),
        )

    @classmethod
    def from_env(cls, models: ModelSettings, cost_sink: CostSink = no_cost) -> "DeepSeekLLM":
        return cls(models, Secrets().deepseek_api_key.get_secret_value(), cost_sink)

    def _model(self, tier: Tier) -> str:
        return getattr(self.models, tier)

    def _cost(self, model: str, usage: dict[str, Any]) -> float:
        miss, hit, out = self.models.llm_prices.get(model, (0.0, 0.0, 0.0))
        hit_tokens = usage.get("prompt_cache_hit_tokens", 0)
        miss_tokens = usage.get(
            "prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - hit_tokens
        )
        return (
            miss_tokens * miss + hit_tokens * hit + usage.get("completion_tokens", 0) * out
        ) / 1_000_000

    def complete(self, messages: list[dict[str, Any]], tier: Tier, json_mode: bool) -> str:
        model = self._model(tier)
        body: dict[str, Any] = {"model": model, "messages": messages}
        if model != "deepseek-reasoner":
            body["temperature"] = self.models.temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = request_with_retry(self.http, "POST", "/chat/completions", json=body).json()
        self.cost_sink(self._cost(model, data.get("usage") or {}), model)
        return data["choices"][0]["message"].get("content") or ""

    def structured(self, system: str, user: str, schema: type[T], tier: Tier = "bulk") -> T:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": f"{system}\n\n{schema_instructions(schema)}"},
            {"role": "user", "content": user},
        ]
        content = ""
        for attempt in range(2):
            content = self.complete(messages, tier, json_mode=True)
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                if attempt == 1:
                    raise LLMOutputError(f"{schema.__name__}: invalid output twice: {exc}") from exc
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"That JSON was invalid:\n{exc}\nReturn corrected JSON only.",
                    },
                ]
        raise AssertionError("unreachable")
