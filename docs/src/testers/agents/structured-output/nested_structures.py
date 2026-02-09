# @sniptest filename=nested_structures.py
# @sniptest show=19-25
from notte_sdk import NotteClient
from pydantic import BaseModel


class Address(BaseModel):
    street: str
    city: str
    zip_code: str


class Company(BaseModel):
    name: str
    address: Address
    employees: int | None


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract company information", response_format=Company)

    if result.success and result.answer:
        company = Company.model_validate_json(result.answer)
        print(company.name)
        print(company.address.city)
