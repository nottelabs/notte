import pytest
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.controller.actions import (
    ClickAction,
    FillAction,
    GotoAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)


@pytest.fixture
def session():
    return NotteSession(config=NotteSessionConfig().disable_perception().headless().disable_web_security())


@pytest.mark.asyncio
async def test_huggingface_model_search(session: NotteSession):
    async with session as page:
        _ = await page.act(GotoAction(url="https://huggingface.co/models"))
        _ = await page.act(FillAction(id="I1", value="sentiment analysis"))
        _ = await page.act(ClickAction(id="L17"))
        _ = await page.act(ClickAction(id="L12"))
        _ = await page.act(ScrollDownAction(amount=None))
        _ = await page.act(ScrollDownAction(amount=None))
        _ = await page.act(ScrollDownAction(amount=None))
        _ = await page.act(ScrollUpAction(amount=500))


@pytest.mark.asyncio
async def test_google_search(session: NotteSession):
    async with session as page:
        _ = await page.act(GotoAction(url="https://www.google.com"))
        if not page.snapshot.dom_node.find("I1"):
            # agree to cookies if menu is present
            _ = await page.act(ClickAction(id="B3"))
        _ = await page.act(FillAction(id="I1", value="test_query"))
        _ = await page.act(SelectDropdownOptionAction(id="I1", option_id="O2"))


@pytest.mark.asyncio
async def test_reddit_fill_search_and_click(session: NotteSession):
    async with session as page:
        _ = await page.act(GotoAction(url="https://www.reddit.com"))
        _ = await page.act(WaitAction(time_ms=1000))
        _ = await page.act(FillAction(id="I1", value="browser-use", press_enter=True))
        _ = await page.act(ClickAction(id="B1"))
        _ = await page.act(ClickAction(id="B4"))
        _ = await page.act(WaitAction(time_ms=5000))
        _ = await page.act(ClickAction(id="L4"))


@pytest.mark.asyncio
async def test_bbc_click_cookie_policy_link(session: NotteSession):
    async with session as page:
        obs = await page.act(GotoAction(url="https://www.bbc.com"))
        assert len(obs.metadata.tabs) == 1
        obs = await page.act(ClickAction(id="L1"))
        assert len(obs.metadata.tabs) == 2
        obs = await page.act(ScrapeAction())
        assert obs.data is not None
        assert obs.data.markdown is not None
        assert "BBC" in obs.data.markdown
        assert "cookies" in obs.data.markdown


@pytest.mark.asyncio
async def test_wikipedia_search(session: NotteSession):
    async with session as page:
        _ = await page.act(GotoAction(url="https://www.wikipedia.org/"))
        _ = await page.act(FillAction(id="I1", value="Nadal"))
        _ = await page.act(ClickAction(id="L11"))
        _ = await page.act(ScrapeAction())


@pytest.mark.asyncio
async def test_allrecipes_search(session: NotteSession):
    async with session as page:
        _ = await page.act(GotoAction(url="https://www.allrecipes.com"))
        consent_cookie = page.snapshot.dom_node.find("B3")
        if consent_cookie and "Consent" in consent_cookie.text:
            _ = await page.act(ClickAction(id="B3"))
        _ = await page.act(FillAction(id="I1", value="chicken breast and quinoa"))
        _ = await page.act(ClickAction(id="B1"))
        _ = await page.act(ScrapeAction())
        _ = await page.act(GotoAction(url="https://www.allrecipes.com/recipe/215076/chicken-with-quinoa-and-veggies/"))
        _ = await page.act(ScrollDownAction(amount=500))
