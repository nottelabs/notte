# @sniptest filename=complex_types.py
from notte_sdk import NotteClient
from pydantic import BaseModel


class SearchParams(BaseModel):
    url: str
    query: str
    max_results: int = 10


def run(params: SearchParams):
    # params is validated against SearchParams model
    client = NotteClient()
    # Use params.url, params.query, etc.
