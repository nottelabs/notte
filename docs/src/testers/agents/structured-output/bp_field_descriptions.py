from pydantic import BaseModel, Field


class Product(BaseModel):
    name: str = Field(description="Product title/name")
    price: float = Field(description="Current selling price in USD")
    original_price: float | None = Field(description="Original price before discount, if any")
