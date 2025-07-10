import pytest
from run import BenchmarkTask, run_task  # pyright: ignore[reportImplicitRelativeImport]

import notte

tasks = [
    {
        "task": "find the top news headline",
        "url": "https://news.google.com",
    },
    {
        "task": "find a linear algebra meme",
        "url": "https://findthatmeme.com/",
    },
    {
        "task": "find out where steve jobs was born",
        "url": "https://wikipedia.org",
    },
    {
        "task": "get the current weather in New York",
        "url": "https://www.accuweather.com/",
    },
    {
        "task": "look up the definition of 'entropy'",
        "url": "https://www.merriam-webster.com",
    },
    {
        "task": "find the current price of TSLA stock",
        "url": "https://finance.yahoo.com/",
    },
    {
        "task": "check the latest post on Hacker News",
        "url": "https://news.ycombinator.com",
    },
]


@pytest.fixture(scope="module")
def session():
    sess = notte.Session(headless=True)
    sess.start()
    yield sess

    sess.stop()


@pytest.mark.parametrize("task", tasks)
def test_run(task, session):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    btask = BenchmarkTask.model_validate(task)
    resp = run_task(session, btask)  # pyright: ignore[reportUnknownArgumentType]
    assert resp
