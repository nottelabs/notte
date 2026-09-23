import asyncio

import pytest

import notte

SHOP_URL = "https://shop.notte.test/"
SHOP_HTML = """<!doctype html>
<html lang="en">
<head><title>Cap shop</title></head>
<body>
    <a href="#cart" id="cart-link">Go to cart</a>
    <h1>Cap</h1>
    <button onclick="document.getElementById('cart').textContent = 'Cap added to cart'; this.disabled = true">
        Add Cap to cart
    </button>
    <section id="cart" aria-label="Cart">Your cart is empty</section>
</body>
</html>
"""


@pytest.fixture
def shop_session():
    # Serve a controlled page so bot protection and shop changes cannot break fallback tests.
    with notte.Session() as session:

        async def fulfill_shop(route):
            await route.fulfill(status=200, content_type="text/html", body=SHOP_HTML)

        asyncio.run(session.page.route(f"{SHOP_URL}**", fulfill_shop))
        assert session.execute(type="goto", url=SHOP_URL).success
        _ = session.observe()
        yield session


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


def test_chapter_success_does_not_spawn_agent(mock_agent_run, shop_session):
    with notte.AgentFallback(shop_session, "Go to cart") as chapter:
        res = shop_session.execute(type="click", selector="#cart-link")
        assert res.success is True

    assert shop_session.page.url == f"{SHOP_URL}#cart"
    assert mock_agent_run["count"] == 0
    assert chapter.success is True
    assert len(chapter.steps) == 1
    assert "Go to cart" in chapter.task


def test_chapter_failure_triggers_agent(mock_agent_run, shop_session):
    with notte.AgentFallback(shop_session, "Go to cart") as chapter:
        res = shop_session.execute(type="click", id="INVALID_ACTION_ID")
        assert res.success is False

    # Agent should have been invoked exactly once with the task as task
    assert mock_agent_run["count"] == 1
    assert "Go to cart" in mock_agent_run["last_kwargs"]["task"]

    assert chapter.success is True
    assert chapter.agent_response is not None
    assert len(chapter.steps) == 1, chapter.steps


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_chapter_with_agent_fix(shop_session):
    with notte.AgentFallback(shop_session, "Add Cap to cart", max_steps=3) as chapter:
        assert shop_session.execute(type="goto", url=f"{SHOP_URL}products/cap").success
        res = shop_session.execute(type="click", id="X1")  # force agent to spawn because ID is not found
        assert res.success is False

    assert chapter.agent_response is not None
    assert chapter.success is True
    assert asyncio.run(shop_session.page.locator("#cart").inner_text()) == "Cap added to cart"
