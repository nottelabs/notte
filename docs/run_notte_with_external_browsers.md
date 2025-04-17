# How to run Notte with external browsers ?

Notte is designed to be used with the browsers it provides by default.

However, it is possible to use your own browsers by providing a `BrowserWindow` instance to the `Agent`.

Here is an example of how to use the `SteelSessionsHandler` to create a `BrowserWindow` and use it to run a task with Notte.

```python
from notte_integrations.sessions.steel import SteelSessionsHandler
from notte_browser.window import BrowserWindow
from notte_agent import Agent

handler = SteelSessionsHandler()
await handler.start()
window=BrowserWindow(handler=handler)
agent = await Agent(window=window)
await agent.run("go to x.com and describe what you see")
await handler.stop()
```

## Supported browsers

- [Steel](https://steel.dev/)
- [Browserbase](https://browserbase.com/)
- [Anchor](https://anchorbrowser.io/)
