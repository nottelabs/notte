import os

import pytest
from dotenv import load_dotenv
from notte_browser.session import NotteSession
from notte_core.actions import ScrapeAction
from notte_sdk.client import NotteClient
from pydantic import BaseModel


class PricingPlan(BaseModel):
    name: str
    price_per_month: int | None = None
    features: list[str]


class PricingPlans(BaseModel):
    plans: list[PricingPlan]


def test_scraping_markdown():
    _ = load_dotenv()
    with NotteSession() as page:
        data = page.scrape(url="https://www.notte.cc")
        assert data.markdown is not None


@pytest.mark.asyncio
async def test_scraping_response_format():
    _ = load_dotenv()
    async with NotteSession() as page:
        data = await page.ascrape(url="https://www.notte.cc", response_format=PricingPlans)
        assert data.structured is not None
        assert data.structured.success
        assert data.structured.data is not None
        plans = PricingPlans.model_validate(data.structured.data)
        assert len(plans.plans) == 3
        assert plans == data.structured.get()


@pytest.mark.asyncio
async def test_scraping_custom_instructions():
    _ = load_dotenv()
    async with NotteSession() as page:
        data = await page.ascrape(url="https://www.notte.cc", instructions="Extract the pricing plans from the page")
        assert data.structured is not None
        assert data.structured.success
        assert data.structured.data is not None
        assert data.structured.get() == data.structured.data.model_dump()


def test_sdk_scraping_markdown():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    data = client.scrape(url="https://www.notte.cc")
    assert data.markdown is not None


def test_sdk_scraping_response_format():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    data = client.scrape(url="https://www.notte.cc", response_format=PricingPlans)
    assert data.structured is not None
    assert data.structured.success
    assert data.structured.data is not None
    assert isinstance(data.structured.data, PricingPlans)


@pytest.mark.asyncio
async def test_readme_async_scraping_example():
    _ = load_dotenv()
    async with NotteSession() as page:
        data = await page.ascrape(url="https://www.notte.cc")
        assert data.markdown is not None


def test_readme_sync_scraping_example():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Session() as page:
        data = page.scrape(url="https://www.notte.cc")
        assert data.markdown is not None


def test_obs_after_scrape_contains_data():
    _ = load_dotenv()
    with NotteSession(enable_perception=False) as page:
        _ = page.observe(url="https://www.notte.cc")
        res = page.step(ScrapeAction(instructions="Extract the pricing plans from the page"))
        assert res.data is not None
        assert res.data.markdown is not None
        obs = page.observe()
        assert obs.data is not None
        assert obs.data.markdown is not None
        assert obs.data == res.data
