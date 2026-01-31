# @sniptest filename=structured_data_response.py
# @sniptest show=3-17

from notte_sdk import NotteClient
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float


client = NotteClient()
url = "https://example.com/product"
product = client.scrape(url, response_format=Product)

# Access the extracted data
print(f"Name: {product.name}, Price: {product.price}")
