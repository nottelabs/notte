import os
from typing import Any

import pytest
from dotenv import load_dotenv
from notte_browser.session import NotteSession
from notte_core.data.space import StructuredData
from notte_sdk.client import NotteClient
from notte_sdk.types import ScrapeRequest
from pydantic import BaseModel


class PricingPlan(BaseModel):
    name: str
    price_per_month: float | None = None
    features: list[str]


class PricingPlans(BaseModel):
    plans: list[PricingPlan]


@pytest.fixture
def pricing_plans_json():
    return {
        "type": "object",
        "required": ["plans"],
        "properties": {
            "plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "description": "Name of the plan"},
                        "price_per_month": {"type": "string", "description": "Price of the plan (with currency)"},
                        "features": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of features included in this plan",
                        },
                    },
                },
            }
        },
    }


def test_scraping_markdown():
    _ = load_dotenv()
    with NotteSession() as session:
        result = session.execute(type="goto", url="https://www.notte.cc/pricing")
        assert result.success
        markdown = session.scrape()
        assert isinstance(markdown, str)
        assert len(markdown) > 0


@pytest.mark.asyncio
async def test_scraping_response_format():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute(type="goto", url="https://www.notte.cc/pricing")
        assert result.success
        structured = await session.ascrape(
            instructions="Extract the pricing plans from the page", response_format=PricingPlans
        )
        assert structured.success
        assert structured.data is not None
        plans = PricingPlans.model_validate(structured.data)
        assert len(plans.plans) >= 1
        assert plans == structured.get()


@pytest.mark.asyncio
async def test_scraping_custom_instructions():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute(type="goto", url="https://www.notte.cc/pricing")
        assert result.success
        structured = await session.ascrape(instructions="Extract the pricing plans from the page")
        assert structured.success
        assert structured.data is not None
        assert structured.get() == structured.data


@pytest.mark.asyncio
async def test_scraping_custom_instructions_and_response_format():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute(type="goto", url="https://www.notte.cc/pricing")
        assert result.success
        structured = await session.ascrape(
            instructions="Extract the pricing plans from the page", response_format=PricingPlans
        )
        assert structured.success
        assert structured.data is not None
        assert structured.get() == structured.data


@pytest.mark.flaky(reruns=3, reruns_delay=2)
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
    structured = client.scrape(url="https://www.notte.cc/pricing", response_format=PricingPlans)
    assert structured.success
    assert structured.data is not None
    assert isinstance(structured.data, PricingPlans)


def test_sdk_scraping_response_format_json(pricing_plans_json: dict[str, Any]):
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    request = ScrapeRequest.model_validate(dict(response_format=pricing_plans_json))
    assert request.response_format is not None
    structured = client.scrape(url="https://www.notte.cc/pricing", response_format=request.response_format)
    assert structured.success
    assert structured.data is not None
    assert isinstance(structured.data, request.response_format)
    assert structured.data.plans is not None
    assert len(structured.data.plans) >= 1


@pytest.mark.asyncio
async def test_readme_async_scraping_example():
    _ = load_dotenv()
    async with NotteSession() as session:
        result = session.execute(type="goto", url="https://www.notte.cc/pricing")
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
async def test_scraping_structured_data():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Session() as session:
        _ = session.execute({"type": "goto", "url": "https://gymbeam.pl"})
        data = session.scrape(instructions="Extract the company name")
        assert isinstance(data, StructuredData)
        assert data.success
        assert isinstance(data.data, dict)
