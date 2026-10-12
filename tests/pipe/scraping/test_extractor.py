"""Structured scraping goes through the StructuredExtractor protocol; the browser itself never calls an LLM."""

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_browser.errors import StructuredExtractorNotAvailableError
from notte_browser.scraping.pipe import DataScrapingPipe
from notte_core.common.config import ScrapingType
from notte_core.data.extraction import StructuredExtractor
from notte_core.data.space import DictBaseModel, StructuredData
from notte_sdk.types import ScrapeParams
from pydantic import BaseModel


class RecordingExtractor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def extract(
        self,
        *,
        url: str,
        document: str,
        response_format: type[BaseModel] | None,
        instructions: str | None,
        model: str | None = None,
        use_link_placeholders: bool = True,
    ) -> StructuredData[BaseModel]:
        self.calls.append(dict(url=url, document=document, instructions=instructions, model=model))
        return StructuredData[BaseModel](success=True, data=DictBaseModel({"title": "t"}))


def _snapshot() -> Any:
    snapshot = MagicMock()
    snapshot.metadata.url = "https://example.com"
    return snapshot


def _pipe(extractor: StructuredExtractor | None = None) -> DataScrapingPipe:
    data_pipe = DataScrapingPipe(type=ScrapingType.MARKDOWNIFY, extractor=extractor)
    data_pipe.scrape_markdown = AsyncMock(return_value="# page")  # type: ignore[method-assign]
    return data_pipe


def test_recording_extractor_satisfies_protocol() -> None:
    assert isinstance(RecordingExtractor(), StructuredExtractor)


def test_scrape_params_accepts_model() -> None:
    params = ScrapeParams(instructions="extract", model="vertex_ai/gemini-3.1-flash-lite")
    assert params.model == "vertex_ai/gemini-3.1-flash-lite"
    assert ScrapeParams(instructions="extract").model is None


@pytest.mark.asyncio
async def test_structured_scrape_hands_markdown_and_model_to_extractor() -> None:
    extractor = RecordingExtractor()
    space = await _pipe(extractor).forward(
        MagicMock(), _snapshot(), ScrapeParams(instructions="extract", model="openai/gpt-4o")
    )
    assert extractor.calls == [
        dict(url="https://example.com", document="# page", instructions="extract", model="openai/gpt-4o")
    ]
    assert space.structured is not None and space.structured.success


@pytest.mark.asyncio
async def test_markdown_scrape_never_resolves_an_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "notte_llm", None)  # any import of notte_llm would now fail
    space = await _pipe().forward(MagicMock(), _snapshot(), ScrapeParams())
    assert space.markdown == "# page"
    assert space.structured is None


@pytest.mark.asyncio
async def test_structured_scrape_without_extractor_or_notte_llm_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "notte_llm", None)
    with pytest.raises(StructuredExtractorNotAvailableError, match=r"notte\[llm\]"):
        _ = await _pipe().forward(MagicMock(), _snapshot(), ScrapeParams(instructions="extract"))
