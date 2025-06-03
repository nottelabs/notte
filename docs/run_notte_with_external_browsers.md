# How to run Notte with external browsers ?

Notte is designed to be used with the browsers it provides by default.

However, it is possible to use your own browsers by providing a `BrowserWindow` instance to the `Agent`.

Here is an example of how to setup `Steel` as the base session manager for Notte Agents.

> [!NOTE]
> You need to install the `notte-integrations` package to be able to use the `SteelSessionsManager`.

```python
from notte_integrations.sessions import configure_sessions_manager
import notte


from dotenv import load_dotenv

_ = load_dotenv()

# you need to export the STEEL_API_KEY environment variable
configure_sessions_manager("steel")

with notte.Session() as session:
    agent = notte.Agent(session=session)
    result = agent.run(task="go to x.com and describe what you see")
```

## Supported browsers

- [Steel](https://steel.dev/)
- [Browserbase](https://browserbase.com/)
- [Anchor](https://anchorbrowser.io/)
