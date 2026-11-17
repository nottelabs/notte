import asyncio
import json
import sys
import urllib.request

import traceroot
from hn_openai import top_stories
from notte_sdk import NotteClient
from traceroot import Dataset, Integration, evaluate_async

HN_API = "https://hacker-news.firebaseio.com/v0"

dataset = Dataset("Hacker News front page", key="hacker-news-front-page")
dataset.add({"task": "Visit https://news.ycombinator.com and return the top 3 stories with their points."})
dataset.add({"task": "Visit https://news.ycombinator.com and return the top 5 stories with their points."})
dataset.add({"task": "Visit https://news.ycombinator.com and return the stories ranked 4 to 6 with their points."})


def front_page_titles() -> set[str]:
    with urllib.request.urlopen(f"{HN_API}/topstories.json", timeout=30) as resp:
        ids = json.load(resp)[:30]
    titles = set()
    for item_id in ids:
        with urllib.request.urlopen(f"{HN_API}/item/{item_id}.json", timeout=30) as resp:
            titles.add(json.load(resp)["title"].strip().lower())
    return titles


def backed_by_front_page(input, output, expected=None) -> float:
    """Share of the answer's stories whose title is on the live Hacker News front page."""
    stories = output["stories"]
    if not stories:
        return 0.0
    titles = front_page_titles()
    return sum(story["title"].strip().lower() in titles for story in stories) / len(stories)


def make_task(broken: bool):
    async def task(input):
        with NotteClient().Session(max_duration_minutes=5) as session:
            with traceroot.using_attributes(session_id=session.session_id):
                return await top_stories(session.session_id, broken, input["task"])

    return task


async def main(broken: bool) -> None:
    result = await evaluate_async(
        name="hacker-news-reader",
        dataset=dataset,
        task=make_task(broken),
        scorers=[backed_by_front_page],
        candidate_version="broken" if broken else "fixed",
        max_concurrency=1,
    )
    print(result.summary())


if __name__ == "__main__":
    traceroot.initialize(integrations=[Integration.OPENAI_AGENTS])
    try:
        with asyncio.Runner() as runner:
            runner.run(main(broken="--broken" in sys.argv))
    finally:
        traceroot.shutdown()
