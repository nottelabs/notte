# @sniptest filename=pydantic_model.py
# @sniptest show=3-18

from notte_sdk import NotteClient
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float
    description: str


client = NotteClient()
product = client.scrape(
    "https://example.com/product", response_format=Product, instructions="Extract the product details"
)

print(f"Name: {product.name}, Price: {product.price}")
