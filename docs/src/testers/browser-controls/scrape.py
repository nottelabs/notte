# @sniptest filename=scrape.py
from notte_sdk import NotteClient
from pydantic import BaseModel

client = NotteClient()


class Product(BaseModel):
    name: str
    price: float


with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Get page markdown
    markdown = session.scrape()

    # Extract with instructions
    data = session.scrape(instructions="Extract all product names and prices")

    # Structured extraction (wrap list in a model)
    products = session.scrape(response_format=Product, instructions="Extract all products")
