# @sniptest filename=use_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Use an existing profile in a session
with client.Session(
    profile={"id": "notte-profile-abc123", "persist": False}
) as session:
    # Session loads saved browser state from the profile
    session.execute(type="goto", url="https://example.com")
