from notte_sdk import NotteClient
from pydantic import BaseModel

client = NotteClient()


class Product(BaseModel):
    name: str
    price: float
    in_stock: bool


with client.Session() as session:
    agent = client.Agent(session=session)

    result = agent.run(
        task="Extract product information",
        url="https://example.com/product/123",
        response_format=Product,
    )

    # Parse and access
    if result.success and result.answer:
        product = Product.model_validate_json(result.answer)
        print(f"{product.name}: ${product.price}")
        if product.in_stock:
            print("Available!")
