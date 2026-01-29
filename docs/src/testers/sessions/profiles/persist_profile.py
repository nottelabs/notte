# @sniptest filename=persist_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Create a new profile
profile = client.profiles.create(name="github-login")

# Use profile with persist=True to save browser state
with client.Session(
    profile={"id": profile.profile_id, "persist": True}
) as session:
    # Navigate and perform login
    session.execute(type="goto", url="https://github.com/login")
    session.execute(type="fill", selector='input[name="login"]', value="username")
    session.execute(type="fill", selector='input[name="password"]', value="password")
    session.execute(type="click", selector='input[type="submit"]')
    # Browser state is saved to profile when session ends
