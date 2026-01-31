# @sniptest filename=structured_scrape.py
from notte_sdk import NotteClient
from pydantic import BaseModel


class PricingPlan(BaseModel):
    name: str
    price_per_month: int | None = None
    features: list[str]


class PricingPlans(BaseModel):
    plans: list[PricingPlan]


client = NotteClient()

# plans is a PricingPlans instance directly
# > note that scrape() can raise ScrapeFailedError if extraction fails
plans = client.scrape(
    url="https://www.notte.cc", instructions="Extract the pricing plans from the page", response_format=PricingPlans
)
