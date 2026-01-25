from pydantic import BaseModel


class Product(BaseModel):
    name: str  # Always required
    price: float  # Always required
    discount: float | None = None  # Might not exist
    rating: float | None = None  # Might not exist
