# @sniptest filename=complex_types.py
from notte_sdk import NotteClient
from pydantic import BaseModel


class SearchParams(BaseModel):
    url: str
    query: str
    max_results: int = 10


def run(params: dict):
    # Variables arrive as plain JSON values: validate them yourself
    search = SearchParams.model_validate(params)
    client = NotteClient()
    # Use search.url, search.query, etc.
