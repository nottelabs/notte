# @sniptest filename=job_listings.py
# @sniptest show=6-19
from pydantic import BaseModel

from notte_sdk import NotteClient


class JobPosting(BaseModel):
    title: str
    company: str
    location: str
    salary_range: str | None
    job_type: str  # "Full-time", "Part-time", etc.
    posted_date: str
    requirements: list[str]


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(
        task="Extract job posting information",
        response_format=JobPosting,
    )
