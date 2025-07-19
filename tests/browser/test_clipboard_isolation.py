import asyncio

import pytest
from notte_browser.session import NotteSession
from notte_core.common.config import PerceptionType

from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service


@pytest.fixture
def mock_llm_service() -> MockLLMService:
    return MockLLMService(mock_response="")


async def simulate_paste(page: NotteSession, text: str) -> None:
    """Helper function to simulate paste operation in a page."""
    await page.window.page.evaluate(
        """
    (text) => {
        // Store in isolated clipboard
        window.__isolatedClipboard = text;

        // Create new DataTransfer object
        const dataTransfer = new DataTransfer();
        dataTransfer.setData('text/plain', window.__isolatedClipboard);

        // Make sure element is focused
        if (document.activeElement) {
            // Create and dispatch the paste event
            const pasteEvent = new ClipboardEvent('paste', {
                clipboardData: dataTransfer,
                bubbles: true,
                cancelable: true
            });

            // Dispatch event on the focused element
            document.activeElement.dispatchEvent(pasteEvent);

            // If the event was not cancelled, manually insert the text
            if (!pasteEvent.defaultPrevented) {
                const selection = document.getSelection();
                const range = selection.getRangeAt(0);
                range.deleteContents();
                range.insertNode(document.createTextNode(text));
            }
        }
    }
    """,
        text,
    )


async def try_access_clipboard(page: NotteSession) -> str:
    """Helper function to attempt accessing clipboard data."""
    await page.window.page.evaluate("""
    () => {
        try {
            const dataTransfer = new DataTransfer();

            // Try to access any potentially leaked clipboard data
            if (window.__isolatedClipboard) {
                console.log("Found leaked clipboard: " + window.__isolatedClipboard);
                dataTransfer.setData('text/plain', window.__isolatedClipboard);
            } else {
                console.log("No clipboard data found in this context");
                return;
            }

            document.activeElement.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dataTransfer,
                bubbles: true,
                cancelable: true
            }));
        } catch (e) {
            console.error("Error during paste attempt:", e);
        }
    }
    """)

    return await page.window.page.evaluate("() => document.querySelector(\"textarea[name='q']\").value")


@pytest.mark.skip(reason="Skip on CICD because it's failing to often")
@pytest.mark.asyncio
async def test_clipboard_isolation(patch_llm_service):
    """Test that clipboard data doesn't leak between browser contexts."""
    # Create two separate Notte environments
    page1 = NotteSession(
        headless=True,
    )
    page2 = NotteSession(
        headless=True,
    )

    test_text = "I love banana"
    url = "https://www.google.com"
    selector = 'textarea[name="q"]'

    async with page1 as p1, page2 as p2:
        # Set up test pages
        _ = await p1.aexecute(type="goto", value=url)
        _ = await p2.aexecute(type="goto", value=url)

        _ = await p1.aobserve(perception_type=PerceptionType.FAST)
        _ = await p2.aobserve(perception_type=PerceptionType.FAST)

        for page in [p1, p2]:
            print(page.snapshot.dom_node.interaction_nodes())
            cookie_node = page.snapshot.dom_node.find("B2")
            if cookie_node is not None:
                _ = await page.aexecute(type="click", action_id="B2", enter=False)  # reject cookies

        # Wait for search box and click it in both contexts
        _ = await p1.window.page.wait_for_selector(selector)
        _ = await p1.window.page.click(selector)
        _ = await p2.window.page.wait_for_selector(selector)
        _ = await p2.window.page.click(selector)

        # Simulate paste in first context
        await simulate_paste(p1, test_text)
        await asyncio.sleep(2)

        # Try to access clipboard in second context multiple times
        for attempt in range(5):
            # Navigate to fresh page each time to ensure clean state
            _ = await p2.aexecute(type="goto", value=url)
            _ = await p2.window.page.wait_for_selector(selector)
            _ = await p2.window.page.click(selector)

            # Try to access clipboard
            search_value = await try_access_clipboard(p2)

            # Assert no clipboard leakage
            assert search_value == "", f"Clipboard leakage detected on attempt {attempt + 1}: '{search_value}'"

            # Small delay between attempts
            await asyncio.sleep(0.5)
