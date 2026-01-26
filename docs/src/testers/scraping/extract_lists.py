# @sniptest filename=extract_lists.py
# @sniptest show=4-24
from typing import cast

from notte_sdk import NotteClient
from pydantic import BaseModel


class Article(BaseModel):
    title: str
    url: str
    summary: str


class ArticleList(BaseModel):
    articles: list[Article]


client = NotteClient()
result = client.scrape(
    "https://news.example.com", response_format=ArticleList, instructions="Extract all articles from the homepage"
)

articles = cast(ArticleList, result.data)
for article in articles.articles:
    print(f"{article.title}: {article.url}")
