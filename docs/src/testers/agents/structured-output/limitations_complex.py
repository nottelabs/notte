# @sniptest filename=limitations_complex.py
# @sniptest show=6-16
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float


# Difficult for agents
class ComplexStructure(BaseModel):
    nested: dict[str, list[dict[str, Product]]]


# Better - flatten or simplify
class SimplifiedStructure(BaseModel):
    products: list[Product]
    categories: list[str]
