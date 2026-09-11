from notte_sdk import NotteClient

client = NotteClient()

try:
    with client.Session() as session:
        page = session.page
        page.goto("https://example.com")

        # Simulate an error
        raise ValueError("Something went wrong!")

except ValueError as e:
    print(f"Automation failed: {e}")
    # Session is still automatically stopped

print("Session was cleaned up despite the error")
