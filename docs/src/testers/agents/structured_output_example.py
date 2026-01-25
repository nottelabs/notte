# @sniptest filename=structured_output_example.py
from notte_sdk import NotteClient
from pydantic import BaseModel

client = NotteClient()


class ContactInfo(BaseModel):
    email: str
    phone: str | None


with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract contact information", response_format=ContactInfo)
