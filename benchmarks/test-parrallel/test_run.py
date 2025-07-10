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
        "url": "https://google.com",
    },
    {
        "task": "find out where steve jobs was born",
        "url": "https://wikipedia.org",
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
