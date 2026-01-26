# @sniptest filename=ecommerce_extraction.py
# @sniptest show=6-21
from pydantic import BaseModel

from notte_sdk import NotteClient


class ProductListing(BaseModel):
    name: str
    price: float
    original_price: float | None
    rating: float
    review_count: int
    availability: str
    seller: str


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(
        task="Extract product listing information",
        url="https://store.example.com/products/laptop",
        response_format=ProductListing,
    )
