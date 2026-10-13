# @sniptest filename=save_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Start a session without a profile, or with a read-only one
with client.Session() as session:
    session.execute(type="goto", url="https://github.com/login")
    # ... log in ...

    # Save the current browser state into a new profile; the session keeps running
    profile = session.save_profile(name="github-login")
    print(profile.profile_id, profile.persisted_domains)

    # Later saves can overwrite the same profile
    session.save_profile(profile_id=profile.profile_id)
