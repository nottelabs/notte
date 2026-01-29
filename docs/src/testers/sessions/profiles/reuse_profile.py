# @sniptest filename=reuse_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Reuse a previously saved profile (read-only)
with client.Session(
    profile={"id": "notte-profile-abc123", "persist": False}
) as session:
    # Navigate directly - already authenticated!
    session.execute(type="goto", url="https://github.com")

    # Perform actions as logged-in user
    obs = session.observe()
    print(f"Page title: {obs.metadata.title}")
