from pydantic import BaseModel


# Difficult for agents
class ComplexStructure(BaseModel):
    nested: dict[str, list[dict[str, Product]]]


# Better - flatten or simplify
class SimplifiedStructure(BaseModel):
    products: list[Product]
    categories: list[str]
