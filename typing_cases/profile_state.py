"""Cases for `profiles.state_set()` (checked by basedpyright).

Lines ending in `# expect-error` must be reported; every other line must type-check.
Keep this file free of runtime side effects; checkers only need the annotations.
"""

from __future__ import annotations

from notte_sdk import NotteClient
from notte_sdk._generated.models import PlaywrightStorageItem, PlaywrightStorageOrigin
from playwright.sync_api import StorageState


def _check_state_set(client: NotteClient, state: StorageState) -> None:
    # A Playwright export's origins, as storage_state() returns them.
    _ = client.profiles.state_set("profile", origins=state.get("origins"))
    _ = client.profiles.state_set(
        "profile", origins=[{"origin": "https://example.com", "localStorage": [{"name": "a", "value": "b"}]}]
    )
    _ = client.profiles.state_set(
        "profile",
        origins=[
            PlaywrightStorageOrigin(
                origin="https://example.com", localStorage=[PlaywrightStorageItem(name="a", value="b")]
            )
        ],
    )
    _ = client.profiles.state_set("profile", origins=[{"origin": "https://example.com"}])  # expect-error
