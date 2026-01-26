# @sniptest filename=limitations_not_suitable.py
# @sniptest show=11-13
from pydantic import BaseModel

from notte_sdk import NotteClient


# Don't do this - use plain text response instead
class Explanation(BaseModel):
    answer: str


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    # Do this instead
    result = agent.run(task="Explain how this product works")
    print(result.answer)  # Natural language explanation
