import pytest
from notte_browser.llm.service import LLMService
from notte_browser.scraping import schema as schema_module
from notte_browser.session import NotteSession
from pydantic import BaseModel

EXTRACTION_MODEL = "vertex_ai/gemini-3.1-flash-lite"


class PageTitle(BaseModel):
    title: str


@pytest.mark.asyncio
async def test_scrape_with_chosen_model(monkeypatch: pytest.MonkeyPatch) -> None:
    used_models: list[str] = []
    original = schema_module.SchemaScrapingPipe

    def recording_pipe(llmserve: LLMService) -> schema_module.SchemaScrapingPipe:
        used_models.append(llmserve.base_model)
        return original(llmserve=llmserve)

    async with NotteSession(headless=True) as page:
        # Record only extractors built per call, not the session's shared default one.
        monkeypatch.setattr(schema_module, "SchemaScrapingPipe", recording_pipe)
        _ = await page.aexecute(type="goto", url="https://example.com/")
        data = await page.ascrape(
            instructions="Extract the main heading of the page",
            response_format=PageTitle,
            model=EXTRACTION_MODEL,
        )

    assert used_models == [EXTRACTION_MODEL]
    assert "example domain" in data.title.lower()
