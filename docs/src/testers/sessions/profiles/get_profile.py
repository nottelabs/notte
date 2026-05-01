# @sniptest filename=get_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Get profile details
profile = client.profiles.get("notte-profile-abc123")

print(f"Profile ID: {profile.profile_id}")
print(f"Profile Name: {profile.name}")
print(f"Created At: {profile.created_at}")
