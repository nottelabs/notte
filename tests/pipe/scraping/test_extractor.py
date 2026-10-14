"""Structured scraping goes through the StructuredExtractor protocol; the browser itself never calls an LLM."""

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import notte_browser.scraping.pipe
import pytest
from notte_browser.errors import StructuredExtractorNotAvailableError
from notte_browser.scraping.pipe import DataScrapingPipe
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


@pytest.fixture(autouse=True)
def page_markdown(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value="# page")
    monkeypatch.setattr(notte_browser.scraping.pipe, "page_markdown", mock)
    return mock


def _pipe(extractor: StructuredExtractor | None = None) -> DataScrapingPipe:
    return DataScrapingPipe(extractor=extractor)


def test_recording_extractor_satisfies_protocol() -> None:
    assert isinstance(RecordingExtractor(), StructuredExtractor)


def test_scrape_params_accepts_model() -> None:
    params = ScrapeParams(instructions="extract", model="vertex_ai/gemini-3.5-flash")
    assert params.model == "vertex_ai/gemini-3.5-flash"
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


@pytest.mark.asyncio
async def test_structured_scrape_reads_the_same_markdown_as_a_plain_scrape(page_markdown: AsyncMock) -> None:
    window, snapshot = MagicMock(), _snapshot()
    params = ScrapeParams(instructions="extract", only_main_content=True)
    _ = await _pipe(RecordingExtractor()).forward(window, snapshot, params)
    page_markdown.assert_awaited_once_with(window, snapshot, params)
