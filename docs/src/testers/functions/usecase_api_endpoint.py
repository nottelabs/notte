# @sniptest filename=contact_extractor.py
from notte_sdk import NotteClient


# contact_extractor.py
def run(company_url: str):
    client = NotteClient()

    with client.Session() as session:
        session.execute(type="goto", url=company_url)

        contact_info = session.scrape(instructions="Extract contact email and phone")

        return contact_info


# Now callable from any service
# GET /functions/{id}/runs/start?variables={"company_url": "..."}
