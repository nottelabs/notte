from pydantic import BaseModel


class Article(BaseModel):
    title: str
    author: str | None  # May not always be present
    date: str | None
    content: str
