# @sniptest filename=nested_structures.py
# @sniptest show=4-26

from notte_sdk import NotteClient
from pydantic import BaseModel


class Address(BaseModel):
    street: str
    city: str
    country: str


class Company(BaseModel):
    name: str
    description: str
    address: Address
    employee_count: int | None


client = NotteClient()
company = client.scrape(
    "https://example.com/about", response_format=Company, instructions="Extract company information including address"
)

print(Company.address.city)
