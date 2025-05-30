# How to run Notte with external browsers ?

Notte is designed to be used with the browsers it provides by default.

However, it is possible to use your own browsers by providing a `BrowserWindow` instance to the `Agent`.

Here is an example of how to use the `SteelSessionsManager` to create a `BrowserWindow` and use it to run a task with Notte.

> [!NOTE]
> You need to install the `notte-integrations` package to be able to use the `SteelSessionsManager`.

```python
from notte_integrations.sessions import SteelSessionsManager
import notte


# you need to export the STEEL_API_KEY environment variable
from dotenv import load_dotenv

_ = load_dotenv()

SteelSessionsManager.configure()
with notte.Session() as session:
    agent = notte.Agent(session=session)
    result = agent.run("go to x.com and describe what you see")
```

## Supported browsers

- [Steel](https://steel.dev/)
- [Browserbase](https://browserbase.com/)
- [Anchor](https://anchorbrowser.io/)
