# @sniptest filename=selenium_frames.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page
    page.goto("https://example.com")

    # Get frame by selector
    frame = page.frame_locator("iframe#content")

    # Interact with elements inside frame
    frame.locator("button").click()

    # Get text from frame
    text = frame.locator("h1").inner_text()
    print(f"Frame heading: {text}")
