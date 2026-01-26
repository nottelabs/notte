# @sniptest filename=field_validation.py
# @sniptest show=6-22
from pydantic import BaseModel, Field, field_validator

from notte_sdk import NotteClient


class Product(BaseModel):
    name: str = Field(min_length=1)
    price: float = Field(gt=0)  # Must be positive
    rating: float = Field(ge=0, le=5)  # 0-5 range

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v > 10000:
            raise ValueError("Price seems unreasonably high")
        return v


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(
        task="Extract product",
        response_format=Product,
    )
