# Notte SDK Tutorial

## Manage your sessions


```python
from notte_core.sdk.client import NotteClient

client = NotteClient(api_key="<your_api_key>")

# start you session
session = client.sessions.start(
    timeout_minutes=5,
)
# get the session status
status = client.sessions.status(session.session_id)
# list your active sessions
active_sessions = client.sessions.list()

# visualize your session (open browser with debug_url)
client.sessions.viewer(session.session_id)
# stop your session
client.sessions.stop(session.session_id)
```

## Connect over CDP

```python
from patchright.sync_api import sync_playwright
from notte_sdk import NotteClient

client = NotteClient(api_key="<your-api-key>")
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

you can also easily visualize the live session using `session.viewer(). This will open a new browser tab with the session in action.



## Manage your agents

```python

# start an agent
agent = client.agents.run(
    task="What is the capital of France?",
    url="https://www.google.com",
)
# get the agent status
status = client.agents.status(agent.agent_id)
# list your agents
agents = client.agents.list()
# stop an agent
client.agents.stop(agent_id=agent.agent_id)
```

Note that starting an agent also starts a session which is automatically stopped when the agent completes its tasks (or is stopped).


## Execute actions in a session

The notte sdk also allows you to `observe` a web page and its actions, `scrape` the page content as well as `execute` actions in a running session.

```python

# start a session
with client.Session() as page:
    # observe a web page
    obs = page.observe(url="https://www.google.com")
    # select random link action and click it
    action = obs.space.sample(role='link')
    data = page.step(action_id=action.id)
    # scrape the page content
    data = page.scrape(url="https://www.google.com")
    # print the scraped content
    print(data.markdown)
```
