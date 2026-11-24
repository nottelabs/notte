# @sniptest filename=import_state.py
# @sniptest show=1-42
from notte_sdk import NotteClient
from notte_sdk.types import Cookie
from playwright.sync_api import StorageState

client = NotteClient()

# The result of Playwright's context.storage_state() on your previous provider
state: StorageState = {
    "cookies": [
        {
            "name": "session_id",
            "value": "abc123",
            "domain": "example.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    ],
    "origins": [
        {"origin": "https://example.com", "localStorage": [{"name": "theme", "value": "dark"}]},
    ],
}

profile = client.profiles.create(name="imported-login")

# Notte takes local storage as {origin: {key: value}}, so convert storage_state()'s lists
imported = client.profiles.state_set(
    profile.profile_id,
    cookies=[Cookie.model_validate(cookie) for cookie in state["cookies"]],
    local_storage={
        origin["origin"]: {item["name"]: item["value"] for item in origin["localStorage"]}
        for origin in state["origins"]
    },
)
print(imported.cookies_count, imported.local_storage_origins)

# Sessions that use the profile start with the imported state
with client.Session(profile={"id": profile.profile_id}) as session:
    session.execute(type="goto", url="https://example.com")
    theme = session.evaluate_js("localStorage.getItem('theme')")

results = [imported.cookies_count, imported.local_storage_origins, theme]
_ = client.profiles.delete(profile.profile_id)
