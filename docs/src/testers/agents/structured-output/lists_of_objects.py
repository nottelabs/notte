# @sniptest filename=lists_of_objects.py
# @sniptest show=1-28
from notte_sdk import NotteClient
from pydantic import BaseModel


class Review(BaseModel):
    author: str
    rating: int
    comment: str


class ReviewList(BaseModel):
    reviews: list[Review]


client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(
        task="Extract all product reviews",
        response_format=ReviewList,
    )

    # Iterate over reviews
    if result.success and result.answer:
        data = ReviewList.model_validate_json(result.answer)
        for review in data.reviews:
            print(f"{review.author}: {review.rating}/5")
            print(review.comment)
