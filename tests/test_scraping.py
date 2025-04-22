import os

import pytest
from dotenv import load_dotenv
from notte_browser.env import NotteEnv
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
    async with NotteEnv() as env:
        obs = await env.scrape(url="https://www.notte.cc")
        assert obs.data is not None
        assert obs.data.markdown is not None


@pytest.mark.asyncio
async def test_scraping_response_format():
    async with NotteEnv() as env:
        obs = await env.scrape(url="https://www.notte.cc", response_format=PricingPlans)
        assert obs.data is not None
        assert obs.data.structured is not None
        assert obs.data.structured.success
        assert obs.data.structured.data is not None
        data = PricingPlans.model_validate(obs.data.structured.data)
        assert len(data.plans) == 4


@pytest.mark.asyncio
async def test_scraping_custom_instructions():
    async with NotteEnv() as env:
        obs = await env.scrape(url="https://www.notte.cc", instructions="Extract the pricing plans from the page")
        assert obs.data is not None
        assert obs.data.structured is not None
        assert obs.data.structured.success
        assert obs.data.structured.data is not None


def test_sdk_scraping_markdown():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    obs = client.env.scrape(url="https://www.notte.cc")
    assert obs.data is not None
    assert obs.data.markdown is not None


@pytest.mark.skip(reason="TODO: re-enable after deploying new version of API")
def test_sdk_scraping_response_format():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    obs = client.env.scrape(url="https://www.notte.cc", response_format=PricingPlans)
    assert obs.data is not None
    assert obs.data.structured is not None
    assert obs.data.structured.success
    assert obs.data.structured.data is not None
    assert isinstance(obs.data.structured.data, PricingPlans)
