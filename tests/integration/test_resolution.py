import pytest
from notte.actions.base import Action
from notte.env import NotteEnv
from notte.pipe.resolution import ActionNodeResolutionPipe

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


async def _test_action_node_resolution_pipe(url: str) -> None:
    errors: list[str] = []
    total_count = 0
    async with NotteEnv(headless=True) as env:
        _ = await env.observe(url, list_next=False)

        action_node_resolution_pipe = ActionNodeResolutionPipe(browser=env._browser)
        context = env._context
        if context is None:
            raise ValueError("Context is None")

        for node in context.interaction_nodes():
            total_count += 1
            if node.id is None:
                raise ValueError("Node id is None")

            action = Action(
                id=node.id,
                description="does not matter",
                category="interaction",
            )
            try:
                action = await action_node_resolution_pipe.forward(action, [], context)
            except Exception as e:
                errors.append(f"Error for node {node.id}: {e}")

    assert total_count > 0, "No nodes found"
    error_text = "\n".join(errors)
    assert len(error_text) == 0, f"Percentage of errors: {len(errors) / total_count * 100:.2f}%\n Errors:\n{error_text}"


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


async def test_bbc() -> None:
    """Test resolution pipe with BBC homepage"""
    await _test_action_node_resolution_pipe("https://www.bbc.com")


async def test_allrecipes() -> None:
    """Test resolution pipe with Allrecipes homepage"""
    await _test_action_node_resolution_pipe("https://www.allrecipes.com")


# async def test_amazon():
#     """Test resolution pipe with Amazon homepage"""
#     await _test_action_node_resolution_pipe("https://www.amazon.com")


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
