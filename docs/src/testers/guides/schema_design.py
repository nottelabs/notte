# @sniptest filename=schema_design.py
from pydantic import BaseModel


class Product(BaseModel):
    product_url: str
    name: str
    price: float | None = None
    description: str | None = None
    image_url: str | None = None


class ProductList(BaseModel):
    products: list[Product]
