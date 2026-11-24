import asyncio
import functools
import html
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import traceroot
from hn_openai import BROKEN_INSTRUCTIONS, INSTRUCTIONS, top_stories
from traceroot import Dataset, Integration, evaluate_async

HN_API = "https://hacker-news.firebaseio.com/v0"

dataset = Dataset("Hacker News front page", key="hacker-news-front-page")
dataset.add({"task": "Visit https://news.ycombinator.com and return the top 3 stories with their points."})
dataset.add({"task": "Visit https://news.ycombinator.com and return the top 5 stories with their points."})
dataset.add({"task": "Visit https://news.ycombinator.com and return the stories ranked 4 to 6 with their points."})


def fetch_json(path: str):
    with urllib.request.urlopen(f"{HN_API}/{path}", timeout=30) as resp:
        return json.load(resp)


@functools.cache
def front_page_titles() -> frozenset[str]:
    """Titles on the Hacker News front page, fetched once per evaluation run."""
    ids = fetch_json("topstories.json")[:30]
    with ThreadPoolExecutor(max_workers=10) as pool:
        items = pool.map(lambda i: fetch_json(f"item/{i}.json"), ids)
        # The API returns titles as HTML, and a story deleted since the ID list was read has no title.
        return frozenset(html.unescape(item["title"]).strip().lower() for item in items if item and "title" in item)


def backed_by_front_page(input, output, expected=None) -> float:
    """Share of the answer's stories whose title is on the live Hacker News front page.

    Points and ranks change between the agent's run and this check, so they are not compared.
    """
    stories = output["stories"]
    if not stories:
        return 0.0
    return sum(story["title"].strip().lower() in front_page_titles() for story in stories) / len(stories)


if __name__ == "__main__":
    broken = "--broken" in sys.argv
    instructions = BROKEN_INSTRUCTIONS if broken else INSTRUCTIONS
    traceroot.initialize(integrations=[Integration.OPENAI_AGENTS])
    try:
        with asyncio.Runner() as runner:
            result = runner.run(
                evaluate_async(
                    name="hacker-news-reader",
                    dataset=dataset,
                    task=lambda case: top_stories(case["task"], instructions),
                    scorers=[backed_by_front_page],
                    candidate_version="broken" if broken else "fixed",
                    max_concurrency=1,
                )
            )
        print(result.summary())
    finally:
        traceroot.shutdown()
