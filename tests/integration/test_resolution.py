import pytest
from loguru import logger
from patchright.async_api import Page

from notte.actions.base import ExecutableAction
from notte.browser.dom_tree import InteractionDomNode
from notte.controller.actions import GotoAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.pipe.resolution.complex_resolution import ComplexActionNodeResolutionPipe

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


async def _test_action_node_resolution_pipe(url: str) -> None:
    errors: list[str] = []
    total_count = 0
    async with NotteEnv(NotteEnvConfig().headless()) as env:
        _ = await env.goto(url)

        action_node_resolution_pipe = ComplexActionNodeResolutionPipe(window=env._window)

        for node in env.snapshot.interaction_nodes():
            total_count += 1
            param_values = None if not node.id.startswith("I") else "some_value"
            try:
                action = ExecutableAction.parse(node.id, param_values)
                action = await action_node_resolution_pipe.forward(action, env.snapshot)
            except Exception as e:
                errors.append(f"Error for node {node.id}: {e}")

    assert total_count > 0, "No nodes found"
    error_text = "\n".join(errors)
    assert len(error_text) == 0, f"Percentage of errors: {len(errors) / total_count * 100:.2f}%\n Errors:\n{error_text}"


async def check_xpath_resolution_v2(page: Page, inodes: list[InteractionDomNode]) -> tuple[list[str], int]:
    from notte.pipe.preprocessing.dom.locate import locale_element_in_iframes, selectors_through_shadow_dom

    smap = {inode.id: inode for inode in inodes}
    empty_xpath: list[str] = []
    resolution_errors: list[str] = []
    total_count = 0
    for id, node in smap.items():
        selectors = node.computed_attributes.selectors
        if selectors is None:
            raise ValueError(f"Selectors for node {id} are None")
        xpath = selectors.xpath_selector
        total_count += 1
        if len(xpath) == 0:
            logger.error(f"[Xpath Error] for element id {id}. Xpath is empty")
            empty_xpath.append(id)
            continue
        locator = page.locator(f"xpath={xpath}")
        if await locator.count() != 1:
            if selectors.in_shadow_root:
                selectors = selectors_through_shadow_dom(node)
                logger.info(f"Node {id} is in shadow root. Retry with new xpath: {selectors.xpath_selector}")
                locator = page.locator(f"xpath={selectors.xpath_selector}")
                if await locator.count() == 1:
                    continue
            if selectors.in_iframe:
                logger.info(f"Node {id} is in iframe. Retry with new xpath: {selectors.xpath_selector}")
                frame = await locale_element_in_iframes(page, selectors)
                locator = frame.locator(f"xpath={xpath}")
                if await locator.count() == 1:
                    continue
            resolution_errors.append(
                (
                    f"Node Id {id} has {await locator.count()} "
                    f"inShadowRoot={selectors.in_shadow_root} elements and xpath {xpath}"
                )
            )
            logger.error(
                (
                    f"[Xpath Resolution Error] Cannot resolve node Id {id} with "
                    f"inShadowRoot={selectors.in_shadow_root} elements and xpath {xpath} "
                )
            )
    logger.error(f"Total count: {total_count}")
    logger.error(f"Empty xpath: {empty_xpath}")
    logger.error(f"Resolution errors: {resolution_errors}")
    return resolution_errors, total_count


async def _test_action_node_resolution_pipe_v2(url: str, headless: bool = True) -> None:
    async with NotteEnv(config=NotteEnvConfig().disable_perception().headless()) as env:
        _ = await env.act(GotoAction(url="https://www.reddit.com"))
        page = env._window.page
        inodes = env.snapshot.interaction_nodes()
        resolution_errors, total_count = await check_xpath_resolution_v2(page, inodes)
        if len(resolution_errors) > 0:
            raise ValueError(
                (
                    f"Resolution % of errors: {len(resolution_errors) / total_count * 100:.2f}%"
                    f"\nErrors:\n{resolution_errors}"
                )
            )


async def test_phantombuster() -> None:
    """Test resolution pipe with Phantombuster login page"""
    await _test_action_node_resolution_pipe("https://phantombuster.com/login")


# Add more test cases as needed
async def test_google() -> None:
    """Test resolution pipe with Google homepage"""
    await _test_action_node_resolution_pipe("https://www.google.com")


async def test_google_flights() -> None:
    """Test resolution pipe with Google Flights homepage"""
    await _test_action_node_resolution_pipe("https://www.google.com/flights")


async def test_google_maps() -> None:
    """Test resolution pipe with Google Maps homepage"""
    await _test_action_node_resolution_pipe("https://www.google.com/maps")


async def test_google_news() -> None:
    """Test resolution pipe with Google News homepage"""
    await _test_action_node_resolution_pipe("https://news.google.com")


async def test_google_translate() -> None:
    """Test resolution pipe with Google Translate homepage"""
    await _test_action_node_resolution_pipe("https://translate.google.com")


async def test_linkedin() -> None:
    """Test resolution pipe with LinkedIn homepage"""
    await _test_action_node_resolution_pipe("https://www.linkedin.com")


async def test_instagram() -> None:
    """Test resolution pipe with Instagram homepage"""
    await _test_action_node_resolution_pipe("https://www.instagram.com")


async def test_notte() -> None:
    """Test resolution pipe with Notte homepage"""
    await _test_action_node_resolution_pipe("https://notte.cc")


@pytest.mark.skip(reason="BBC is not too slow and faulty due to timeouts")
async def test_bbc() -> None:
    """Test resolution pipe with BBC homepage"""
    await _test_action_node_resolution_pipe("https://www.bbc.com")


async def test_allrecipes() -> None:
    """Test resolution pipe with Allrecipes homepage"""
    await _test_action_node_resolution_pipe("https://www.allrecipes.com")


@pytest.mark.skip(reason="Amazon is too slow and faulty due to timeouts")
async def test_amazon():
    """Test resolution pipe with Amazon homepage"""
    await _test_action_node_resolution_pipe("https://www.amazon.com")


async def test_apple() -> None:
    """Test resolution pipe with Apple homepage"""
    await _test_action_node_resolution_pipe("https://www.apple.com")


async def test_arxiv() -> None:
    """Test resolution pipe with Arxiv homepage"""
    await _test_action_node_resolution_pipe("https://arxiv.org")


async def test_booking() -> None:
    """Test resolution pipe with Booking.com homepage"""
    await _test_action_node_resolution_pipe("https://www.booking.com")


async def test_coursera() -> None:
    """Test resolution pipe with Coursera homepage"""
    await _test_action_node_resolution_pipe("https://www.coursera.org")


async def test_cambridge_dictionary() -> None:
    """Test resolution pipe with Cambridge Dictionary homepage"""
    await _test_action_node_resolution_pipe("https://dictionary.cambridge.org")


async def test_espn() -> None:
    """Test resolution pipe with ESPN homepage"""
    await _test_action_node_resolution_pipe("https://www.espn.com")


async def test_github() -> None:
    """Test resolution pipe with Github homepage"""
    await _test_action_node_resolution_pipe("https://www.github.com")


async def test_huggingface() -> None:
    """Test resolution pipe with HuggingFace homepage"""
    await _test_action_node_resolution_pipe("https://www.huggingface.co")


async def test_wolframalpha() -> None:
    """Test resolution pipe with WolframAlpha homepage"""
    await _test_action_node_resolution_pipe("https://www.wolframalpha.com")
