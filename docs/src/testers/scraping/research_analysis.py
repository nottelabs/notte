# @sniptest filename=research_analysis.py
from notte_sdk import NotteClient
from pydantic import BaseModel


class ResearchPaper(BaseModel):
    title: str
    authors: list[str]
    abstract: str
    publication_date: str | None
    citations: int | None


client = NotteClient()
result = client.scrape("https://papers.example.com/paper/123", response_format=ResearchPaper)
