# @sniptest filename=error_handling.py
from notte_sdk import NotteClient
from pydantic import BaseModel, ValidationError


class Product(BaseModel):
    name: str
    price: float


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract product data", response_format=Product)

    # result.answer is a JSON string: validate it against your model
    if not result.success or result.answer is None:
        print(f"Agent failed: {result.answer}")
    else:
        try:
            product = Product.model_validate_json(result.answer)
        except ValidationError as e:
            print(f"Agent returned invalid data: {e}")
