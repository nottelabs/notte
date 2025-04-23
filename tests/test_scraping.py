import os

import pytest
from dotenv import load_dotenv
from notte_browser.session import NotteSession
from notte_sdk.client import NotteClient
from pydantic import BaseModel

_ = load_dotenv()


class PricingPlan(BaseModel):
    name: str
    price_per_month: int | None
    features: list[str]


class PricingPlans(BaseModel):
    plans: list[PricingPlan]


@pytest.mark.asyncio
async def test_scraping_markdown():
    async with NotteSession() as page:
        data = await page.scrape(url="https://www.notte.cc")
        assert data.markdown is not None


@pytest.mark.asyncio
async def test_scraping_response_format():
    async with NotteSession() as page:
        data = await page.scrape(url="https://www.notte.cc", response_format=PricingPlans)
        assert data is not None
        assert data.structured is not None
        assert data.structured.success
        assert data.structured.data is not None
        plans = PricingPlans.model_validate(data.structured.data)
        assert len(plans.plans) == 4
        assert plans == data.structured.get()


@pytest.mark.asyncio
async def test_scraping_custom_instructions():
    async with NotteSession() as page:
        data = await page.scrape(url="https://www.notte.cc", instructions="Extract the pricing plans from the page")
        assert data.structured is not None
        assert data.structured.success
        assert data.structured.data is not None
        assert data.structured.get() == data.structured.data.model_dump()


def test_sdk_scraping_markdown():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    data = client.sessions.page.scrape(url="https://www.notte.cc")
    assert data.markdown is not None


def test_sdk_scraping_response_format():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    data = client.sessions.page.scrape(url="https://www.notte.cc", response_format=PricingPlans)
    assert data.structured is not None
    assert data.structured.success
    assert data.structured.data is not None
    assert isinstance(data.structured.data, PricingPlans)


@pytest.mark.asyncio
async def test_readme_async_scraping_example():
    async with NotteSession() as page:
        data = await page.scrape(url="https://www.notte.cc")
        assert data.markdown is not None


def test_readme_sync_scraping_example():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Session() as page:
        data = page.scrape(url="https://www.notte.cc")
        assert data.markdown is not None
