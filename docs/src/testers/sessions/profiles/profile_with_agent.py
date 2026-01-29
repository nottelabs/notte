# @sniptest filename=profile_with_agent.py
from notte_sdk import NotteClient

client = NotteClient()

# Use a profile with an agent
with client.Session(
    profile={"id": "notte-profile-abc123", "persist": False}
) as session:
    agent = client.Agent(session=session, max_steps=10)

    # Agent runs with pre-authenticated session
    response = agent.run(
        task="Go to my GitHub notifications and summarize them",
        url="https://github.com/notifications"
    )

    print(f"Agent response: {response.answer}")
