import json
from datetime import date
from pathlib import Path

import pytest

from seo_engine.config import Settings
from seo_engine.models import Run
from seo_engine.providers.base import DailyCache

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path / "cache")


@pytest.fixture
def cache(settings: Settings) -> DailyCache:
    return DailyCache(settings.cache_dir, today=lambda: date(2026, 9, 24))


@pytest.fixture
def run(settings: Settings) -> Run:
    return Run(page_text="Emitii is a client project workspace for agencies.", settings=settings)
