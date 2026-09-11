from notte_sdk import NotteClient
from pydantic import BaseModel


class HackerNewsPost(BaseModel):
    title: str
    url: str
    points: int
    author: str


class HackerNewsFeed(BaseModel):
    posts: list[HackerNewsPost]


client = NotteClient()

result = client.scrape(
    url="https://news.ycombinator.com",
    response_format=HackerNewsFeed,
    instructions="Extract the top 5 posts from the front page",
)

for i, post in enumerate(result.data.posts, 1):
    print(f"{i}. {post.points} - {post.title}")
