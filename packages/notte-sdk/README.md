# Notte SDK

Python SDK for the [Notte API](https://docs.notte.cc): hosted browser sessions with stealth, CAPTCHA solving and proxies, serverless functions, credential vaults and personas.

## Installation

```bash
pip install notte-sdk
# to drive sessions with Playwright over CDP
pip install 'notte-sdk[playwright]'
```

## Quick start

```python
from notte_sdk import NotteClient

client = NotteClient()  # reads NOTTE_API_KEY

with client.Session(open_viewer=True) as session:
    _ = session.execute(type="goto", url="https://news.ycombinator.com")
    obs = session.observe()
    markdown = session.scrape(only_main_content=True)
```

## What's inside

- `client.Session(...)`: cloud browser sessions (`execute`, `observe`, `scrape`, cookies, file storage, live view, replays) reachable over CDP with `session.cdp_url()`
- `client.Function(...)` / `client.functions`: deploy a Python file with a `run` function and run it on the Notte cloud
- `client.Vault(...)`: store credentials that sessions fill in without exposing them to your code
- `client.Persona(...)`: identities with their own email address and phone number
- `client.scrape(url, ...)`: one-call scraping, with `instructions` / `response_format` for structured output

See the [documentation](https://docs.notte.cc) for the full reference.
