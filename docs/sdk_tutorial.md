# Notte SDK Tutorial

## Manage your sessions

```python
from notte.sdk.client import NotteClient

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
from patchright.async_api import async_playwright
from notte.sdk.client import NotteClient

client = NotteClient(api_key="<your-api-key>")

# start notte session
session = client.sessions.start()
debug_info = client.sessions.debug_info(session.session_id)

# connect using CDP
async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(debug_info.ws_url)
    page = browser.contexts[0].pages[0]
    _ = await page.goto("https://www.google.com")
    screenshot = await page.screenshot(path="screenshot.png")
    # Work with browser here
    await browser.close()

client.sessions.close(session.session_id)
```

you can also easily visualize the session using the `debug_info.debug_url` url. Paste it in your browser to see the session in action.



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
client.agents.stop(agent.agent_id)
```

Note that starting an agent also starts a session which is automatically stopped when the agent completes its tasks (or is stopped).


## Execute actions in a session

The notte sdk also allows you to `observe` a web page and its actions, `scrape` the page content as well as `execute` actions in a running session.

```python

# start a session
session = client.sessions.start()

# observe a web page
obs = client.sessions.observe(session_id=session.session_id, url="https://www.google.com", keep_alive=True)

# execute an action in the session
action = obs.space.sample(role='link')
obs = client.env.step(session_id=session.session_id, action_id=action.id, keep_alive=True)
# scrape the page content
obs = client.sessions.scrape(session_id=session.session_id, keep_alive=True)
# print the scraped content
print(obs.data.markdown)
```
