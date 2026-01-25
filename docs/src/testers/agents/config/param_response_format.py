# @sniptest filename=param_response_format.py
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float
    in_stock: bool


result = agent.run(task="Extract product information", response_format=Product)
