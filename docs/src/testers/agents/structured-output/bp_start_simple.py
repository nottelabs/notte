from pydantic import BaseModel


# Start with minimal model
class Product(BaseModel):
    name: str
    price: float


# Add fields as needed
class DetailedProduct(BaseModel):
    name: str
    price: float
    description: str | None
    specs: dict[str, str] | None
