# How to run Notte with external browsers ?

Notte is designed to be used with the browsers it provides by default.

However, it is possible to use your own browsers by providing a `BrowserWindow` instance to the `Agent`.

Here is an example of how to use the `SteelSessionsManager` to create a `BrowserWindow` and use it to run a task with Notte.

```python
from notte_integrations.sessions.steel import SteelSessionsManager
from notte_agent import Agent

async with SteelSessionsManager() as browser:
    window= await browser.new_window()
    agent = Agent(window=window)
    result = await agent.async_run("go to x.com and describe what you see")
    await window.close()
```

## Supported browsers

- [Steel](https://steel.dev/)
- [Browserbase](https://browserbase.com/)
- [Anchor](https://anchorbrowser.io/)
