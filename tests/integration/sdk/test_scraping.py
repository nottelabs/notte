import os

import pytest
from dotenv import load_dotenv
from notte_browser.session import NotteSession
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
    with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://www.notte.cc"})
        assert result.success
        markdown = session.scrape()
        assert isinstance(markdown, str)
        assert len(markdown) > 0


@pytest.mark.asyncio
async def test_scraping_response_format():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://www.notte.cc"})
        assert result.success
        structured = await session.ascrape(response_format=PricingPlans)
        assert structured.success
        assert structured.data is not None
        plans = PricingPlans.model_validate(structured.data)
        assert len(plans.plans) == 4
        assert plans == structured.get()


@pytest.mark.asyncio
async def test_scraping_custom_instructions():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://www.notte.cc"})
        assert result.success
        structured = await session.ascrape(instructions="Extract the pricing plans from the page")
        assert structured.success
        assert structured.data is not None
        assert structured.get() == structured.data


@pytest.mark.asyncio
async def test_scraping_custom_instructions_and_response_format():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://www.notte.cc"})
        assert result.success
        structured = await session.ascrape(
            instructions="Extract the pricing plans from the page", response_format=PricingPlans
        )
        assert structured.success
        assert structured.data is not None
        assert structured.get() == structured.data


def test_sdk_scraping_markdown():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    data = client.scrape(url="https://www.notte.cc")
    assert isinstance(data, str)
    assert len(data) > 0


def test_sdk_scraping_markdown_no_positional():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    data = client.scrape("https://www.notte.cc")
    assert isinstance(data, str)
    assert len(data) > 0


def test_sdk_scraping_response_format():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    structured = client.scrape(url="https://www.notte.cc", response_format=PricingPlans)
    assert structured.success
    assert structured.data is not None
    assert isinstance(structured.data, PricingPlans)


@pytest.mark.asyncio
async def test_readme_async_scraping_example():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://www.notte.cc"})
        assert result.success
        data = await session.ascrape()
        assert isinstance(data, str)
        assert len(data) > 0


def test_readme_sync_scraping_example():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Session() as session:
        result = session.execute({"type": "goto", "url": "https://www.notte.cc"})
        assert result.success
        data = session.scrape()
        assert isinstance(data, str)
        assert len(data) > 0


@pytest.mark.asyncio
async def test_scraping_images_only():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://gymbeam.pl"})
        assert result.success
        images = await session.ascrape()
        assert len(images) > 0


@pytest.mark.asyncio
async def test_scraping_images_only_false():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute({"type": "goto", "url": "https://gymbeam.pl"})
        assert result.success
        data = await session.ascrape(only_images=False)
        assert isinstance(data, str)
        assert len(data) > 0
