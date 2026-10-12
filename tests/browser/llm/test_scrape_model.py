"""Tests for choosing the extraction model per scrape call."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_browser.llm.service import LLMService
from notte_browser.scraping import schema as schema_module
from notte_browser.scraping.pipe import DataScrapingPipe
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_core.common.config import ScrapingType
from notte_core.data.space import DictBaseModel, StructuredData
from notte_sdk.types import ScrapeParams


def _structured() -> StructuredData[DictBaseModel]:
    return StructuredData[DictBaseModel](success=True, error=None, data=DictBaseModel({"title": "t"}))


def _pipe(monkeypatch: pytest.MonkeyPatch) -> tuple[DataScrapingPipe, list[Any]]:
    data_pipe = DataScrapingPipe(type=ScrapingType.MARKDOWNIFY)
    data_pipe._schema_pipe = SchemaScrapingPipe(llmserve=LLMService(base_model="vertex_ai/gemini-3.5-flash"))  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(data_pipe, "scrape_markdown", AsyncMock(return_value="# page"))
    shared_forward = AsyncMock(return_value=_structured())
    monkeypatch.setattr(data_pipe.get_schema_pipe(), "forward", shared_forward)

    created: list[Any] = []
    original = schema_module.SchemaScrapingPipe

    def spy(llmserve: LLMService) -> Any:
        instance = original(llmserve=llmserve)
        instance.forward = AsyncMock(return_value=_structured())  # type: ignore[method-assign]
        created.append(instance)
        return instance

    monkeypatch.setattr(schema_module, "SchemaScrapingPipe", spy)
    return data_pipe, created


def _snapshot() -> Any:
    snapshot = MagicMock()
    snapshot.metadata.url = "https://example.com"
    return snapshot


def test_scrape_params_accepts_model() -> None:
    params = ScrapeParams(instructions="extract", model="vertex_ai/gemini-3.1-flash-lite")
    assert params.model == "vertex_ai/gemini-3.1-flash-lite"
    assert ScrapeParams(instructions="extract").model is None


@pytest.mark.asyncio
async def test_default_model_uses_shared_schema_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    data_pipe, created = _pipe(monkeypatch)

    _ = await data_pipe.forward(MagicMock(), _snapshot(), ScrapeParams(instructions="extract"))

    assert created == []
    data_pipe.get_schema_pipe().forward.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_chosen_model_uses_per_call_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    data_pipe, created = _pipe(monkeypatch)
    shared_llm = data_pipe.get_schema_pipe().llmserve

    space = await data_pipe.forward(
        MagicMock(), _snapshot(), ScrapeParams(instructions="extract", model="vertex_ai/gemini-3.1-flash-lite")
    )

    assert len(created) == 1
    assert created[0].llmserve.base_model == "vertex_ai/gemini-3.1-flash-lite"
    created[0].forward.assert_awaited_once()
    data_pipe.get_schema_pipe().forward.assert_not_awaited()  # type: ignore[attr-defined]
    assert data_pipe.get_schema_pipe().llmserve is shared_llm
    assert shared_llm.base_model == "vertex_ai/gemini-3.5-flash"
    assert space.structured is not None and space.structured.success
