import pytest

import notte


@pytest.fixture
def mock_agent_run(monkeypatch):
    calls = {"count": 0, "last_kwargs": None}

    async def fake_arun(self, **data):
        calls["count"] += 1
        calls["last_kwargs"] = data

        class Resp:
            success = True
            answer = "ok"

        return Resp()

    monkeypatch.setattr(notte.Agent, "arun", fake_arun, raising=True)
    return calls


def test_chapter_success_does_not_spawn_agent(mock_agent_run):
    with notte.Session() as session:
        _ = session.execute(type="goto", value="https://shop.notte.cc/")
        _ = session.observe()

        with notte.AgentFallback(session, "Go to cart") as chapter:
            _ = session.execute(type="click", id="L1")
        assert chapter.success is True

    assert mock_agent_run["count"] == 0
    assert chapter.success is True
    assert len(chapter.steps) == 1
    assert "Go to cart" in chapter.task


def test_chapter_failure_triggers_agent(mock_agent_run):
    with notte.Session() as session:
        _ = session.execute(type="goto", value="https://shop.notte.cc/")
        _ = session.observe()

        with notte.AgentFallback(session, "Go to cart") as chapter:
            res = session.execute(type="click", id="INVALID_ACTION_ID")
            assert res.success is False

    # Agent should have been invoked exactly once with the task as task
    assert mock_agent_run["count"] == 1
    assert "Go to cart" in mock_agent_run["last_kwargs"]["task"]

    assert chapter.success is True
    assert chapter.agent_response is not None
    assert len(chapter.steps) == 1, chapter.steps


# might fail because of captcha
@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_chapter_with_agent_fix():
    with notte.Session() as session:
        _ = session.execute(type="goto", url="https://shop.notte.cc/")
        _ = session.observe()

        # close modal if it appears but don't fail if it doesn't
        _ = session.execute(type="click", id="B1", raise_on_failure=False)
        _ = session.observe()

        with notte.AgentFallback(session, "Add Cap to cart", max_steps=3) as chapter:
            _ = session.execute(type="click", id="L7")
            res = session.execute(type="click", id="X1")  # force agent to spawn because ID is not found
            assert res.success is False
        assert chapter.success is True
