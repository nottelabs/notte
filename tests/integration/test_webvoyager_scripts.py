import pytest
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.actions.base import (
    ClickAction,
    FillAction,
    GotoAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    WaitAction,
)
from notte_sdk.types import DEFAULT_VIEWPORT_HEIGHT, DEFAULT_VIEWPORT_WIDTH


@pytest.fixture
def config():
    return (
        NotteSessionConfig()
        .disable_perception()
        .headless()
        .disable_web_security()
        .set_viewport(width=DEFAULT_VIEWPORT_WIDTH, height=DEFAULT_VIEWPORT_HEIGHT)
        .set_user_agent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )


@pytest.mark.asyncio
async def test_huggingface_model_search(config: NotteSessionConfig):
    async with NotteSession(config=config) as page:
        _ = await page.act(GotoAction(url="https://huggingface.co/models"))
        _ = await page.act(FillAction(id="I1", value="sentiment analysis"))
        _ = await page.act(WaitAction(time_ms=2000))
        _ = await page.act(ClickAction(id="L17"))
        _ = await page.act(ClickAction(id="L12"))
        _ = await page.act(ScrollDownAction(amount=None))
        _ = await page.act(ScrollDownAction(amount=None))
        _ = await page.act(ScrollDownAction(amount=None))
        _ = await page.act(ScrollUpAction(amount=500))


@pytest.mark.asyncio
async def test_google_search(config: NotteSessionConfig):
    async with NotteSession(config=config) as page:
        _ = await page.act(GotoAction(url="https://www.google.com"))
        if not page.snapshot.dom_node.find("I1"):
            # agree to cookies if menu is present
            _ = await page.act(ClickAction(id="B3"))
        _ = await page.act(FillAction(id="I1", value="test_query"))
        _ = await page.act(ClickAction(id="O2"))


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_reddit_fill_search_and_click(config: NotteSessionConfig):
    async with NotteSession(config=config) as page:
        _ = await page.act(GotoAction(url="https://www.reddit.com"))
        _ = await page.act(WaitAction(time_ms=3000))
        _ = await page.act(FillAction(id="I1", value="browser-use", press_enter=True))
        _ = await page.act(ClickAction(id="B1"))
        _ = await page.act(ClickAction(id="B4"))
        _ = await page.act(WaitAction(time_ms=5000))
        _ = await page.act(ClickAction(id="L4"))


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_bbc_click_cookie_policy_link(config: NotteSessionConfig):
    async with NotteSession(config=config) as page:
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
async def test_wikipedia_search(config: NotteSessionConfig):
    async with NotteSession(config=config) as page:
        _ = await page.act(GotoAction(url="https://www.wikipedia.org/"))
        _ = await page.act(FillAction(id="I1", value="Nadal"))
        _ = await page.act(ClickAction(id="L11"))
        _ = await page.act(ScrapeAction())


@pytest.mark.asyncio
async def test_allrecipes_search(config: NotteSessionConfig):
    async with NotteSession(config=config) as page:
        _ = await page.act(GotoAction(url="https://www.allrecipes.com"))
        consent_cookie = page.snapshot.dom_node.find("B3")
        if consent_cookie and "Consent" in consent_cookie.text:
            _ = await page.act(ClickAction(id="B3"))
        _ = await page.act(FillAction(id="I1", value="chicken breast and quinoa"))
        _ = await page.act(ClickAction(id="B1"))
        _ = await page.act(ScrapeAction())
        _ = await page.act(GotoAction(url="https://www.allrecipes.com/recipe/215076/chicken-with-quinoa-and-veggies/"))
        _ = await page.act(ScrollDownAction(amount=500))
