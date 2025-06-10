# Notte SDK Tutorial

## Manage your sessions


```python
from notte_sdk.client import NotteClient
import os
client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# start you session
session = client.sessions.start(timeout_minutes=5)
# get the session status
status = client.sessions.status(session.session_id)
# list your active sessions
active_sessions = client.sessions.list()
# stop your session
client.sessions.stop(session.session_id)
```

## Connect over CDP

```python
import os
from patchright.sync_api import sync_playwright
from notte_sdk import NotteClient

client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
with client.Session(proxies=False, max_steps=1) as session:
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
> You can also use the `client.sessions.viewer_cdp()` method to open Chrome CDP viewer.



## Manage your agents

```python
from notte_sdk.client import NotteClient
import os
client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# start an agent
agent = client.agents.run(
    task="Summarize the job offers on the Notte careers page.",
    url="https://notte.cc",
    max_steps=10,
)
# get session replay
replay = client.agents.replay(agent.agent_id)
```

Note that starting an agent also starts a session which is automatically stopped when the agent completes its tasks (or is stopped).

You can use a non blocking approach to control the execution flow using the `client.agents.start(...)`, `client.agents.status(...)` and `client.agents.stop(...)` methods.


## Execute actions in a session

The notte sdk also allows you to `observe` a web page and its actions, `scrape` the page content as well as `execute` actions in a running session.

```python
from notte_sdk.client import NotteClient
import os
client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# start a session
with client.Session() as session:
    # observe a web page
    obs = session.observe(url="https://www.google.com")
    # select random id to click
    action = obs.space.sample(type="click")
    data = session.step(action_id=action.id)
    # scrape the page content
    data = session.scrape(url="https://www.google.com")
    # print the scraped content)
    agent = client.Agent(session=session)
    agent.run(
        task="Summarize the content of the page",
        url="https://www.google.com",
    )
    print(data.markdown)
```
