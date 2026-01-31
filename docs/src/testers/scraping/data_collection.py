# @sniptest filename=data_collection.py
from notte_sdk import NotteClient
from pydantic import BaseModel


class ProductInfo(BaseModel):
    name: str
    price: float
    rating: float | None
    reviews_count: int | None


client = NotteClient()

urls = [
    "https://store.example.com/product/1",
    "https://store.example.com/product/2",
]

products: list[ProductInfo] = []
for url in urls:
    data = client.scrape(url, response_format=ProductInfo)
    products.append(data)
