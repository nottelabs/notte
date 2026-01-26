from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Be more specific
    task = "Fill the email input field in the signup form with user@example.com"

    # Or disable vision if causing confusion
    agent = client.Agent(session=session, use_vision=False)
