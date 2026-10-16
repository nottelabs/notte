"""Structured scraping goes through the StructuredExtractor protocol; the browser itself never calls an LLM."""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import notte_browser.scrape
import notte_browser.session as session_module
import pytest
from notte_browser.errors import BrowserNotStartedError, EmptyPageContentError, StructuredExtractorNotAvailableError
from notte_browser.scrape import default_extractor, scrape_page, scrape_snapshot
from notte_browser.session import NotteSession
from notte_core.data import DictBaseModel, StructuredData
from notte_core.extraction import StructuredExtractor
from notte_core.profiling import profiler
from notte_sdk.types import ScrapeParams
from pydantic import BaseModel, RootModel, ValidationError


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
    monkeypatch.setattr(notte_browser.scrape, "page_markdown", mock)
    return mock


def test_recording_extractor_satisfies_protocol() -> None:
    assert isinstance(RecordingExtractor(), StructuredExtractor)


def test_scrape_params_accepts_model() -> None:
    params = ScrapeParams(instructions="extract", model="vertex_ai/gemini-3.5-flash")
    assert params.model == "vertex_ai/gemini-3.5-flash"
    assert ScrapeParams(instructions="extract").model is None


@pytest.mark.asyncio
async def test_structured_scrape_hands_markdown_and_model_to_extractor() -> None:
    extractor = RecordingExtractor()
    space = await scrape_snapshot(
        MagicMock(),
        _snapshot(),
        ScrapeParams(instructions="extract", model="openai/gpt-4o"),
        get_extractor=lambda: extractor,
    )
    assert extractor.calls == [
        dict(url="https://example.com", document="# page", instructions="extract", model="openai/gpt-4o")
    ]
    assert space.structured is not None and space.structured.success


@pytest.mark.asyncio
async def test_markdown_scrape_never_resolves_an_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "notte_llm", None)  # any import of notte_llm would now fail
    space = await scrape_snapshot(MagicMock(), _snapshot(), ScrapeParams(), get_extractor=default_extractor)
    assert space.markdown == "# page"
    assert space.structured is None


@pytest.mark.asyncio
async def test_structured_scrape_without_extractor_or_notte_llm_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "notte_llm", None)
    with pytest.raises(StructuredExtractorNotAvailableError, match=r"notte\[llm\]"):
        _ = await scrape_snapshot(
            MagicMock(), _snapshot(), ScrapeParams(instructions="extract"), get_extractor=default_extractor
        )


@pytest.mark.asyncio
async def test_structured_scrape_reads_the_same_markdown_as_a_plain_scrape(page_markdown: AsyncMock) -> None:
    window, snapshot = MagicMock(), _snapshot()
    params = ScrapeParams(instructions="extract", only_main_content=True)
    _ = await scrape_snapshot(window, snapshot, params, get_extractor=RecordingExtractor)
    page_markdown.assert_awaited_once_with(window, snapshot, params)


@pytest.mark.asyncio
async def test_session_extractor_is_lazy_after_markdown_and_cached_per_session(
    monkeypatch: pytest.MonkeyPatch, page_markdown: AsyncMock
) -> None:
    factory = MagicMock(side_effect=RecordingExtractor)
    monkeypatch.setattr(session_module, "default_extractor", factory)
    window = MagicMock()
    window.snapshot = AsyncMock(return_value=_snapshot())
    session = NotteSession(window=window)
    factory.assert_not_called()
    assert await session.ascrape() == "# page"
    factory.assert_not_called()
    page_markdown.side_effect = ValueError("markdown failed")
    with pytest.raises(ValueError, match="markdown failed"):
        await session.ascrape(instructions="extract")
    factory.assert_not_called()
    page_markdown.side_effect = None
    for _ in range(2):
        assert await session.ascrape(instructions="extract") == {"title": "t"}
    factory.assert_called_once_with()
    assert len(session.trajectory) == 4
    assert await NotteSession(window=window).ascrape(instructions="extract") == {"title": "t"}
    assert factory.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["snapshot", "markdown", "extractor"])
async def test_scrape_retry_scope_includes_extractor_empty_content(
    monkeypatch: pytest.MonkeyPatch, page_markdown: AsyncMock, failure_at: str
) -> None:
    error = EmptyPageContentError(url="https://example.com", nb_retries=3)
    window = MagicMock()
    window.snapshot = AsyncMock(return_value=_snapshot())
    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=StructuredData(data=DictBaseModel(["item"])))
    failure = {"snapshot": window.snapshot, "markdown": page_markdown, "extractor": extractor.extract}[failure_at]
    failure.side_effect = [error, failure.return_value]
    sleep = AsyncMock()
    monkeypatch.setattr(notte_browser.scrape.asyncio, "sleep", sleep)
    data = await scrape_page(window, ScrapeParams(instructions="extract"), get_extractor=lambda: extractor)
    assert data.structured is not None and data.structured.get() == ["item"]
    assert window.snapshot.await_count == 2
    window.snapshot.assert_awaited_with(selector=None, skip_dom=True, screenshot=False)
    sleep.assert_awaited_once_with(2)
    failure.side_effect = error
    window.snapshot.reset_mock()
    sleep.reset_mock()
    with pytest.raises(EmptyPageContentError):
        await scrape_page(window, ScrapeParams(instructions="extract"), get_extractor=lambda: extractor)
    assert window.snapshot.await_count == 4
    assert sleep.await_count == 3


@pytest.mark.asyncio
async def test_injected_extractor_error_return_records_one_event(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock(side_effect=AssertionError("injected extractor must be used"))
    monkeypatch.setattr(session_module, "default_extractor", factory)
    window = MagicMock()
    window.snapshot = AsyncMock(return_value=_snapshot())
    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=StructuredData(success=False, error="bad schema"))
    session = NotteSession(window=window, extractor=extractor)
    result = await session.ascrape(instructions="extract", raise_on_failure=False)
    assert isinstance(result, StructuredData) and not result.success and result.error == "bad schema"
    assert len(session.trajectory) == 1
    factory.assert_not_called()


class PageTitle(BaseModel):
    title: str


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [PageTitle(title="page"), RootModel[list[str]](["item"])])
async def test_session_schema_result_unwraps_and_records_once(data: BaseModel) -> None:
    window = MagicMock()
    window.snapshot = AsyncMock(return_value=_snapshot())
    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=StructuredData(data=data))
    session = NotteSession(window=window, extractor=extractor)
    result = await session.ascrape(response_format=type(data))
    assert result == (data.root if isinstance(data, RootModel) else data)
    assert extractor.extract.await_args.kwargs["response_format"] is type(data)
    assert len(session.trajectory) == 1


@pytest.mark.asyncio
async def test_scrape_validates_params_before_accessing_the_window() -> None:
    session = NotteSession()
    with pytest.raises(ValidationError):
        await session.ascrape(model=123)  # pyright: ignore[reportArgumentType]
    assert len(session.trajectory) == 1


@pytest.fixture
def scrape_spans(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []

    @asynccontextmanager
    async def profile(operation_name: str, *, service_name: str) -> AsyncIterator[None]:
        assert operation_name == "NotteSession._ascrape"
        assert service_name == "execution"
        events.append("start")
        try:
            yield
        finally:
            events.append("end")

    monkeypatch.setattr(profiler, "profile", profile)
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_params", [True, False])
async def test_scrape_profiles_validation_and_unstarted_window_failures(
    scrape_spans: list[str], invalid_params: bool
) -> None:
    session = NotteSession()
    if invalid_params:
        with pytest.raises(ValidationError):
            await session.ascrape(model=123)  # pyright: ignore[reportArgumentType]
    else:
        with pytest.raises(BrowserNotStartedError):
            await session.ascrape()
    assert scrape_spans == ["start", "end"]
    assert len(session.trajectory) == 1


@pytest.mark.asyncio
async def test_scrape_retry_spans_stay_nested(monkeypatch: pytest.MonkeyPatch, scrape_spans: list[str]) -> None:
    window = MagicMock()
    window.snapshot = AsyncMock(
        side_effect=[EmptyPageContentError(url="https://example.com", nb_retries=3), _snapshot()]
    )
    monkeypatch.setattr(notte_browser.scrape.asyncio, "sleep", AsyncMock())
    session = NotteSession(window=window)
    assert await session.ascrape() == "# page"
    assert scrape_spans == ["start", "start", "end", "end"]
    assert len(session.trajectory) == 1
