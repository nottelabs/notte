import asyncio

import pytest

from notte.env import NotteEnv, NotteEnvConfig
from tests.mock.mock_service import MockLLMService


async def simulate_paste(env: NotteEnv, text: str) -> None:
    """Helper function to simulate paste operation in a page."""
    await env._window.page.evaluate(
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


async def try_access_clipboard(env: NotteEnv) -> str:
    """Helper function to attempt accessing clipboard data."""
    await env._window.page.evaluate("""
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

    return await env._window.page.evaluate("() => document.querySelector(\"textarea[name='q']\").value")


@pytest.mark.asyncio
async def test_clipboard_isolation():
    """Test that clipboard data doesn't leak between browser contexts."""
    # Create two separate Notte environments
    env1 = NotteEnv(
        config=NotteEnvConfig().disable_perception().headless().disable_web_security(),
        llmserve=MockLLMService(mock_response=""),
    )
    env2 = NotteEnv(
        config=NotteEnvConfig().disable_perception().headless().disable_web_security(),
        llmserve=MockLLMService(mock_response=""),
    )

    test_text = "I love banana"
    url = "https://www.google.com"
    selector = 'textarea[name="q"]'

    async with env1 as e1, env2 as e2:
        # Set up test pages
        await e1.goto(url)
        await e2.goto(url)

        for env in [e1, e2]:
            print(env.snapshot.dom_node.interaction_nodes())
            cookie_node = env.snapshot.dom_node.find("B2")
            if cookie_node is not None:
                _ = await env.execute("B2", enter=False)  # reject cookies

        # Wait for search box and click it in both contexts
        await e1._window.page.wait_for_selector(selector)
        await e1._window.page.click(selector)
        await e2._window.page.wait_for_selector(selector)
        await e2._window.page.click(selector)

        # Simulate paste in first context
        await simulate_paste(e1, test_text)
        await asyncio.sleep(2)

        # Try to access clipboard in second context multiple times
        for attempt in range(5):
            # Navigate to fresh page each time to ensure clean state
            await e2.goto(url)
            await e2._window.page.wait_for_selector(selector)
            await e2._window.page.click(selector)

            # Try to access clipboard
            search_value = await try_access_clipboard(e2)

            # Assert no clipboard leakage
            assert search_value == "", f"Clipboard leakage detected on attempt {attempt + 1}: '{search_value}'"

            # Small delay between attempts
            await asyncio.sleep(0.5)
