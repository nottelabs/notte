from notte_sdk import NotteClient

client = NotteClient()

session = None

try:
    session = client.Session()
    session.start()

    page = session.page
    page.goto("https://example.com")

    # Your automation code here

except Exception as error:
    print(f"Automation failed: {error}")
finally:
    # This always runs, whether success or failure
    if session is not None:
        session.stop()
        print("Session stopped")
