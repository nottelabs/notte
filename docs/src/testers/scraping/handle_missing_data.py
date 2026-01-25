# @sniptest filename=handle_missing_data.py
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float
    discount_price: float | None = None  # Optional
    rating: float | None = None  # Optional
