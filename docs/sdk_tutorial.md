# Notte SDK Tutorial

## Manage your sessions


```python
from notte_sdk.client import NotteClient
import os
notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# start / stop your session using the context manager
with notte.Session(max_duration_minutes=5) as session:
    # get the session status
    status = session.status()
# list your active sessions
active_sessions = notte.sessions.list()
print(len(active_sessions))
```

## Connect over CDP

```python
import os
from patchright.sync_api import sync_playwright
from notte_sdk import NotteClient

notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
with notte.Session(proxies=False) as session:
    # get cdp url
    cdp_url = session.cdp_url()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        page = browser.contexts[0].pages[0]
        _ = page.goto("https://www.google.com")
        screenshot = page.screenshot(path="screenshot.png")
        assert screenshot is not None
```

you can also easily visualize the live session using `session.viewer()`. This will open a new browser tab with the session in action.

> [!NOTE]
> You can also use the `session.viewer_cdp()` method to open Chrome CDP viewer.


## Record and replay your sessions

```python
from notte_sdk.client import NotteClient

client = NotteClient()
with client.Session() as session:
    _ = session.execute(type="goto", url="https://notte.cc")
    summary = session.scrape(instructions="Summarize what Notte does in two sentences.")
# Retrieve the replay after closing the session
replay = session.replay()
```

The session context manager stops the session when the block exits. Every action executed in the session is recorded, and `session.replay()` returns a presigned URL to the MP4 recording.


## Execute actions in a session

The notte sdk also allows you to `observe` a web page and its actions, `scrape` the page content as well as `execute` actions in a running session.

```python
from notte_sdk.client import NotteClient
import os
import random
notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# start a session
with notte.Session() as session:
    # observe a web page
    result = session.execute(type="goto", url="https://www.google.com")
    obs = session.observe()
    # select random id to click
    action = random.choice([action for action in obs.space.actions if action.type == "click"])
    result = session.execute(action)
    # scrape the page content
    markdown = session.scrape()
    print(markdown)
    # extract structured content from the page with instructions
    summary = session.scrape(instructions="Summarize the content of the page")
    print(summary)
```
