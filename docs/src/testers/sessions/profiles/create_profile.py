# @sniptest filename=create_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Create a profile with optional name
profile = client.profiles.create(name="my-profile")

print(f"Profile created: {profile.profile_id}")
print(f"Profile name: {profile.name}")
