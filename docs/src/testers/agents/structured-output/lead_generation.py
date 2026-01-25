from pydantic import BaseModel


class BusinessLead(BaseModel):
    company_name: str
    contact_email: str | None
    phone: str | None
    website: str
    industry: str
    employee_count: str | None


result = agent.run(
    task="Extract business information from this company page",
    url="https://example.com/about",
    response_format=BusinessLead,
)
