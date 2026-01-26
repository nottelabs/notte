# @sniptest filename=param_response_format.py
# @sniptest show=6-16
from pydantic import BaseModel

from notte_sdk import NotteClient


class Product(BaseModel):
    name: str
    price: float
    in_stock: bool


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract product information", response_format=Product)
