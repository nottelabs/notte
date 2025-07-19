import pytest
from notte_browser.session import NotteSession
from notte_core.actions import (
    ClickAction,
    FillAction,
    GotoAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    WaitAction,
)
from notte_core.common.config import PerceptionType

# .set_user_agent(
#             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#         )


@pytest.mark.asyncio
async def test_huggingface_model_search():
    async with NotteSession() as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(GotoAction(url="https://huggingface.co/models"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(FillAction(id="I1", value="sentiment analysis"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(WaitAction(time_ms=2000))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="L17"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="L12"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrollDownAction(amount=None))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrollDownAction(amount=None))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrollDownAction(amount=None))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrollUpAction(amount=500))


@pytest.mark.asyncio
async def test_google_search():
    async with NotteSession() as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(GotoAction(url="https://www.google.com"))
        _ = await page.aobserve(perception_type=perception_type)
        if not page.snapshot.dom_node.find("I1"):
            # agree to cookies if menu is present
            _ = await page.aexecute(ClickAction(id="B3"))
            _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(FillAction(id="I1", value="test_query"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="O2"))
        _ = await page.aobserve(perception_type=perception_type)


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_reddit_fill_search_and_click():
    async with NotteSession() as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(GotoAction(url="https://www.reddit.com"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(WaitAction(time_ms=3000))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(FillAction(id="I1", value="browser-use", press_enter=True))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="B1"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(WaitAction(time_ms=5000))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="L4"))
        _ = await page.aobserve(perception_type=perception_type)


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_bbc_click_cookie_policy_link():
    async with NotteSession() as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(GotoAction(url="https://www.bbc.com"))
        obs = await page.aobserve(perception_type=perception_type)
        assert len(obs.metadata.tabs) == 1
        _ = await page.aexecute(ClickAction(id="L1"))
        obs = await page.aobserve(perception_type=perception_type)
        assert len(obs.metadata.tabs) == 2
        res = await page.aexecute(ScrapeAction())
        assert res.data is not None
        assert res.data.markdown is not None
        assert "BBC" in res.data.markdown
        assert "cookies" in res.data.markdown


@pytest.mark.asyncio
async def test_wikipedia_search():
    async with NotteSession() as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(GotoAction(url="https://www.wikipedia.org/"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(FillAction(id="I1", value="Nadal"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="L11"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrapeAction())


@pytest.mark.asyncio
async def test_allrecipes_search():
    async with NotteSession() as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(GotoAction(url="https://www.allrecipes.com"))
        _ = await page.aobserve(perception_type=perception_type)
        consent_cookie = page.snapshot.dom_node.find("B3")
        if consent_cookie and "Consent" in consent_cookie.text:
            _ = await page.aexecute(ClickAction(id="B3"))
            _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(FillAction(id="I1", value="chicken breast and quinoa"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ClickAction(id="B1"))
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrapeAction())
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(
            GotoAction(url="https://www.allrecipes.com/recipe/215076/chicken-with-quinoa-and-veggies/")
        )
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(ScrollDownAction(amount=500))
