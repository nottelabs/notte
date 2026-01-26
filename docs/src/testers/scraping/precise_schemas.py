# @sniptest filename=precise_schemas.py
from pydantic import BaseModel


# Good - matches page structure
class GoodProduct(BaseModel):
    name: str
    price: float
    in_stock: bool


# Bad - fields that may not exist
class BadProduct(BaseModel):
    name: str
    price: float
    manufacturer: str  # Page might not have this
    warranty: str  # Page might not have this
