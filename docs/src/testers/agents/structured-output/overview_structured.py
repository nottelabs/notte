# @sniptest filename=overview_structured.py
# @sniptest show=12-14
from pydantic import BaseModel

from notte_sdk import NotteClient


class ContactInfo(BaseModel):
    email: str
    phone: str | None


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Find contact info", response_format=ContactInfo)
    if result.success and result.answer:
        contact = ContactInfo.model_validate_json(result.answer)
        print(contact.email)  # Type-safe access
