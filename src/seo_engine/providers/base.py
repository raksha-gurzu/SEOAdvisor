"""Shared provider plumbing: daily cache, cost sink, retrying HTTP."""

import hashlib
import json
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx

CostSink = Callable[[float, str], None]


def no_cost(usd: float, label: str) -> None:
    """Default sink for callers that do not track cost."""


class DailyCache:
    """JSON cache keyed by (namespace, inputs, date). Never pay twice on the same day."""

    def __init__(self, root: Path, today: Callable[[], date] = date.today) -> None:
        self.root = root
        self.today = today

    def _path(self, namespace: str, key: Any) -> Path:
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()
        return self.root / self.today().isoformat() / namespace / f"{digest[:32]}.json"

    def get(self, namespace: str, key: Any) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, namespace: str, key: Any, value: Any) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


RETRY_STATUS = {429, 500, 502, 503, 504}


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 4,
    backoff_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP call with exponential backoff on transport errors and retryable status codes."""
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
        else:
            if response.status_code not in RETRY_STATUS or attempt == attempts - 1:
                response.raise_for_status()
                return response
        sleep(backoff_s * 2**attempt)
    raise AssertionError("unreachable")
