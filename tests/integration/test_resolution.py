import pytest
from loguru import logger
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.actions.base import GotoAction
from notte_core.actions.percieved import ExecPerceivedAction
from notte_core.browser.dom_tree import InteractionDomNode
from notte_sdk.types import DEFAULT_VIEWPORT_HEIGHT, DEFAULT_VIEWPORT_WIDTH
from patchright.async_api import Page

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def config() -> NotteSessionConfig:
    return (
        NotteSessionConfig()
        .headless()
        .set_viewport(width=DEFAULT_VIEWPORT_WIDTH, height=DEFAULT_VIEWPORT_HEIGHT)
        .disable_perception()
    )


def urls() -> list[str]:
    return [
        "https://www.google.com",
        "https://www.google.com/flights",
        "https://www.google.com/maps",
        "https://news.google.com",
        "https://translate.google.com",
        "https://www.linkedin.com",
        "https://www.instagram.com",
        "https://notte.cc",
        "https://www.bbc.com",
        "https://www.allrecipes.com",
        "https://www.amazon.com",
        "https://www.apple.com",
        "https://arxiv.org",
        "https://www.coursera.org",
        "https://dictionary.cambridge.org",
        "https://www.espn.com",
    ]


@pytest.mark.parametrize(
    "url",
    urls(),
    ids=lambda url: url.replace("https://", "").replace("http://", "").replace("www.", ""),
)
async def test_action_node_resolution_pipe(url: str, config: NotteSessionConfig) -> None:
    errors: list[str] = []
    total_count = 0
    async with NotteSession(config) as page:
        _ = await page.goto(url)

        action_node_resolution_pipe = NodeResolutionPipe()

        for node in page.snapshot.interaction_nodes():
            total_count += 1
            param_values = None if not node.id.startswith("I") else "some_value"
            try:
                action = ExecPerceivedAction(id=node.id, value=param_values)
                action = await action_node_resolution_pipe.forward(action, page.snapshot)
            except Exception as e:
                errors.append(f"Error for node {node.id}: {e}")

    assert total_count > 0, "No nodes found"
    error_text = "\n".join(errors)
    assert len(error_text) == 0, f"Percentage of errors: {len(errors) / total_count * 100:.2f}%\n Errors:\n{error_text}"


async def check_xpath_resolution_v2(page: Page, inodes: list[InteractionDomNode]) -> tuple[list[str], int]:
    from notte_browser.dom.locate import locale_element_in_iframes, selectors_through_shadow_dom

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


async def _test_action_node_resolution_pipe_v2(config: NotteSessionConfig) -> None:
    async with NotteSession(config=config) as page:
        _ = await page.act(GotoAction(url="https://www.reddit.com"))
        inodes = page.snapshot.interaction_nodes()
        resolution_errors, total_count = await check_xpath_resolution_v2(page.window.page, inodes)
        if len(resolution_errors) > 0:
            raise ValueError(
                (
                    f"Resolution % of errors: {len(resolution_errors) / total_count * 100:.2f}%"
                    f"\nErrors:\n{resolution_errors}"
                )
            )
