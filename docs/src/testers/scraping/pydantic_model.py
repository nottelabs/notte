# @sniptest filename=pydantic_model.py
# @sniptest show=4-17
from typing import cast

from notte_sdk import NotteClient
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float
    description: str


client = NotteClient()
result = client.scrape(
    "https://example.com/product", response_format=Product, instructions="Extract the product details"
)

product = cast(Product, result.data)
print(product.name)
print(product.price)
