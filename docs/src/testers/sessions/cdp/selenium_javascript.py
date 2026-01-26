# @sniptest filename=selenium_javascript.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page
    page.goto("https://example.com")

    # Execute JavaScript
    result = page.evaluate("document.title")
    print(f"Title: {result}")

    # Execute complex script
    data = page.evaluate("""
        () => {
            const items = document.querySelectorAll('.item');
            return Array.from(items).map(item => item.textContent);
        }
    """)
    print(f"Items: {data}")

    # Pass arguments to JavaScript
    result = page.evaluate("x => x * 2", 5)
    print(f"Result: {result}")  # 10
