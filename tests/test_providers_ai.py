import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from seo_engine.config import ModelSettings
from seo_engine.providers.embeddings import GEMINI_URL, GeminiEmbeddings
from seo_engine.providers.llm import DeepSeekLLM, LLMOutputError

CHAT = "https://api.deepseek.com/chat/completions"


class Topics(BaseModel):
    topics: list[str]


def _reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {
                "prompt_tokens": 1000,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 1000,
                "completion_tokens": 500,
            },
        },
    )


@respx.mock
def test_structured_validates_and_logs_cost(run) -> None:
    route = respx.post(CHAT).mock(return_value=_reply('{"topics": ["file sharing"]}'))
    llm = DeepSeekLLM(ModelSettings(), "key", cost_sink=run.add_cost)
    out = llm.structured("sys", "page", Topics)
    assert out.topics == ["file sharing"]
    body = json.loads(route.calls[0].request.content)
    assert body["response_format"] == {"type": "json_object"} and body["model"] == "deepseek-chat"
    assert "JSON schema" in body["messages"][0]["content"]
    assert run.cost_usd == pytest.approx((1000 * 0.28 + 500 * 0.42) / 1e6)


@respx.mock
def test_structured_retries_once_then_raises(run) -> None:
    route = respx.post(CHAT).mock(side_effect=[_reply("not json"), _reply('{"topics": ["a"]}')])
    llm = DeepSeekLLM(ModelSettings(), "key", cost_sink=run.add_cost)
    assert llm.structured("sys", "page", Topics).topics == ["a"]
    retry_msgs = json.loads(route.calls[1].request.content)["messages"]
    assert retry_msgs[-1]["role"] == "user" and "invalid" in retry_msgs[-1]["content"]

    respx.post(CHAT).mock(side_effect=[_reply("{}"), _reply('{"wrong": 1}')])
    with pytest.raises(LLMOutputError):
        llm.structured("sys", "page", Topics)


@respx.mock
def test_gemini_embeddings_batch_normalise_and_cache(cache, run) -> None:
    route = respx.post(f"{GEMINI_URL}models/gemini-embedding-001:batchEmbedContents").mock(
        return_value=httpx.Response(
            200, json={"embeddings": [{"values": [3.0, 4.0]}, {"values": [0.0, 2.0]}]}
        )
    )
    emb = GeminiEmbeddings(ModelSettings(), "key", cache, cost_sink=run.add_cost)
    first = emb.embed(["alpha", "beta", "alpha"])
    assert first[0] == pytest.approx([0.6, 0.8]) and first[2] == first[0]
    assert first[1] == pytest.approx([0.0, 1.0])
    sent = json.loads(route.calls[0].request.content)["requests"]
    assert len(sent) == 2 and sent[0]["outputDimensionality"] == 768
    assert emb.embed(["beta"]) == [first[1]]
    assert route.call_count == 1 and len(run.costs) == 1
