# @sniptest filename=lead_generation.py
# @sniptest show=6-20
from pydantic import BaseModel

from notte_sdk import NotteClient


class BusinessLead(BaseModel):
    company_name: str
    contact_email: str | None
    phone: str | None
    website: str
    industry: str
    employee_count: str | None


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(
        task="Extract business information from this company page",
        url="https://example.com/about",
        response_format=BusinessLead,
    )
