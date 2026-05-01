# @sniptest filename=social_media.py
# @sniptest show=6-20
from notte_sdk import NotteClient
from pydantic import BaseModel


class SocialProfile(BaseModel):
    username: str
    display_name: str
    bio: str | None
    follower_count: int
    following_count: int
    post_count: int
    verified: bool


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(
        task="Extract social media profile information",
        response_format=SocialProfile,
    )
