# @sniptest filename=structured_data_response.py
# @sniptest show=6-17
from typing import cast

from notte_sdk import NotteClient
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float


client = NotteClient()
url = "https://example.com/product"
result = client.scrape(url, response_format=Product)

# Access the extracted data
product = cast(Product, result.data)
print(product.name)
