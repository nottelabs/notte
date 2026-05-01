# @sniptest filename=list_profiles.py
from notte_sdk import NotteClient

client = NotteClient()

# List all profiles
profiles = client.profiles.list()

for profile in profiles:
    print(f"- {profile.name}: {profile.profile_id}")

# Filter by name
filtered = client.profiles.list(name="github")
print(f"Found {len(filtered)} profiles matching 'github'")
