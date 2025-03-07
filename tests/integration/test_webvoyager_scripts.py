import pytest

from notte.controller.actions import (
    ClickAction,
    FillAction,
    GotoAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte.env import NotteEnv, NotteEnvConfig


@pytest.fixture
def notte_env():
    return NotteEnv(config=NotteEnvConfig().disable_perception().headless().disable_web_security())


@pytest.mark.asyncio
async def test_huggingface_model_search(notte_env: NotteEnv):
    async with notte_env as env:
        _ = await env.act(GotoAction(url="https://huggingface.co/models"))
        _ = await env.act(FillAction(id="I1", value="sentiment analysis"))
        _ = await env.act(ClickAction(id="L17"))
        _ = await env.act(ClickAction(id="L12"))
        _ = await env.act(ScrollDownAction(amount=None))
        _ = await env.act(ScrollDownAction(amount=None))
        _ = await env.act(ScrollDownAction(amount=None))
        _ = await env.act(ScrollUpAction(amount=500))


@pytest.mark.asyncio
async def test_google_search(notte_env: NotteEnv):
    async with notte_env as env:
        _ = await env.act(GotoAction(url="https://www.google.com"))
        if not env.snapshot.dom_node.find("I1"):
            # agree to cookies if menu is present
            _ = await env.act(ClickAction(id="B3"))
        _ = await env.act(FillAction(id="I1", value="test_query"))
        _ = await env.act(SelectDropdownOptionAction(id="I1", option_id="O2"))


@pytest.mark.asyncio
async def test_reddit_fill_search_and_click(notte_env: NotteEnv):
    async with notte_env as env:
        _ = await env.act(GotoAction(url="https://www.reddit.com"))
        _ = await env.act(WaitAction(time_ms=1000))
        _ = await env.act(FillAction(id="I1", value="browser-use", press_enter=True))
        _ = await env.act(ClickAction(id="B1"))
        _ = await env.act(ClickAction(id="B4"))
        _ = await env.act(WaitAction(time_ms=5000))
        _ = await env.act(ClickAction(id="L4"))


@pytest.mark.asyncio
async def test_bbc_click_cookie_policy_link(notte_env: NotteEnv):
    async with notte_env as env:
        obs = await env.act(GotoAction(url="https://www.bbc.com"))
        assert len(obs.metadata.tabs) == 1
        obs = await env.act(ClickAction(id="L1"))
        assert len(obs.metadata.tabs) == 2
        obs = await env.act(ScrapeAction())
        assert obs.data is not None
        assert obs.data.markdown is not None
        assert "BBC" in obs.data.markdown
        assert "cookies" in obs.data.markdown


@pytest.mark.asyncio
async def test_wikipedia_search(notte_env: NotteEnv):
    async with notte_env as env:
        _ = await env.act(GotoAction(url="https://www.wikipedia.org/"))
        _ = await env.act(FillAction(id="I1", value="Nadal"))
        _ = await env.act(ClickAction(id="L11"))
        _ = await env.act(ScrapeAction())


@pytest.mark.asyncio
async def test_allrecipes_search(notte_env: NotteEnv):
    async with notte_env as env:
        _ = await env.act(GotoAction(url="https://www.allrecipes.com"))
        consent_cookie = env.snapshot.dom_node.find("B3")
        if consent_cookie and "Consent" in consent_cookie.text:
            _ = await env.act(ClickAction(id="B3"))
        _ = await env.act(FillAction(id="I1", value="chicken breast and quinoa"))
        _ = await env.act(ClickAction(id="B1"))
        _ = await env.act(ScrapeAction())
        _ = await env.act(GotoAction(url="https://www.allrecipes.com/recipe/215076/chicken-with-quinoa-and-veggies/"))
        _ = await env.act(ScrollDownAction(amount=500))
