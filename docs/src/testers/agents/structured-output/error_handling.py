# @sniptest filename=error_handling.py
# @sniptest show=13-21
from pydantic import BaseModel, ValidationError

from notte_sdk import NotteClient


class Product(BaseModel):
    name: str
    price: float


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    try:
        result = agent.run(
            task="Extract product data",
            response_format=Product,
        )
        product = result.answer
    except ValidationError as e:
        print(f"Agent returned invalid data: {e}")
