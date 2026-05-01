# @sniptest filename=delete_profile.py
from notte_sdk import NotteClient

client = NotteClient()

# Delete a profile
deleted = client.profiles.delete("notte-profile-abc123")

if deleted:
    print("Profile deleted successfully")
