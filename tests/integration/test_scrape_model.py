import pytest
from notte_browser.session import NotteSession
from notte_llm import LlmExtractor
from pydantic import BaseModel

EXTRACTION_MODEL = "google/gemini-3.5-flash"


class PageTitle(BaseModel):
    title: str


@pytest.mark.asyncio
async def test_scrape_with_chosen_model() -> None:
    # A default other than the chosen model, so the per-call service is observable.
    extractor = LlmExtractor(model="google/gemini-3.8-flash")

    async with NotteSession(headless=True, extractor=extractor) as page:
        _ = await page.aexecute(type="goto", url="https://example.com/")
        data = await page.ascrape(
            instructions="Extract the main heading of the page",
            response_format=PageTitle,
            model=EXTRACTION_MODEL,
        )

    # The chosen model is used for this call only, through a service of its own.
    assert list(extractor._per_call_services) == [EXTRACTION_MODEL]  # pyright: ignore[reportPrivateUsage]
    assert "example domain" in data.title.lower()
