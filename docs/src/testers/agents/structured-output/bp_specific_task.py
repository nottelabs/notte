# @sniptest filename=bp_specific_task.py
# @sniptest show=13-22
from pydantic import BaseModel

from notte_sdk import NotteClient


class Product(BaseModel):
    name: str
    price: float
    in_stock: bool


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)

    # Good - task matches response_format
    result = agent.run(
        task="Extract the product name, price, and stock status",
        response_format=Product,
    )

    # Less clear - agent might not fill all fields
    result = agent.run(
        task="Tell me about this product",
        response_format=Product,
    )
