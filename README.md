# Browser infrastructure for AI agents and web automation

<div align="center">
  <p>
    Stealth cloud browsers, a Playwright-based browser framework, and serverless functions to run your web automations <br/>
    → <a href="https://docs.notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Docs</a> • <a href="https://console.notte.cc/?ref=github" target="_blank" rel="noopener noreferrer">Console</a> • <a href="https://anything.notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Anything API</a> • <a href="https://notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Landing</a> • <a href="https://join.slack.com/t/nottelabs-dev/shared_invite/zt-39a8n6hr9-d_BG7RNfytimSpVo5H03mA" target="_blank" rel="noopener noreferrer">Slack</a> • <a href="https://x.com/nottecore?ref=github" target="_blank" rel="noopener noreferrer">X</a>
  </p>
</div>

<p align="center">
  <img src="docs/logo/bgd.png" alt="Notte Logo" width="100%">
</p>

[![GitHub stars](https://img.shields.io/github/stars/nottelabs/notte?style=social)](https://github.com/nottelabs/notte/stargazers)
[![License: SSPL-1.0](https://img.shields.io/badge/License-SSPL%201.0-blue.svg)](https://spdx.org/licenses/SSPL-1.0.html)
[![npm version](https://img.shields.io/npm/v/notte-sdk?color=blue)](https://www.npmjs.com/package/notte-sdk)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/notte?color=blue)](https://pypi.org/project/notte/)
[![PyPI Downloads](https://static.pepy.tech/badge/notte?color=blue)](https://pepy.tech/projects/notte)

---

# What is Notte?

Notte gives AI agents and scripts a reliable browser. Drive cloud browser sessions with built-in stealth, CAPTCHA solving and proxies, or a local browser with the same API; deploy automations as functions; and keep credentials and identities out of your code. Read more in our documentation [here](https://docs.notte.cc) 🔥

Choose your starting point:

| Product | Use it for |
|---|---|
| [Notte CLI](https://docs.notte.cc/cli-reference/index) | Drive browsers from the terminal, scripts or CI |
| [Notte MCP](https://docs.notte.cc/mcp-server) | Give your coding agent a cloud browser |
| [Browser sessions](#cloud-sessions) | Run Playwright or Puppeteer on stealth cloud browsers |
| [Browser functions](#functions) | Deploy a browser script as an API or scheduled job |
| [Anything API](https://anything.notte.cc) | Turn a described task into a deployed API |
| [Scraping](#scraping) | Extract structured data from a page |

**Open-source core:**
- **[Local browser sessions](#local-sessions)** → A Playwright-based browser that turns pages into actionable observations and clean markdown
- **[Scraping](#scraping)** → Markdown, images or structured data (Pydantic models) from any page

**API service (recommended):**
- **[Stealth browser sessions](#cloud-sessions)** → Hosted browsers with CAPTCHA solving, proxies and anti-detection, reachable over CDP from Playwright, Puppeteer or Selenium
- **[Functions](#functions)** → Deploy a Python automation and run it on demand, on a schedule, or behind an API endpoint
- **[Secrets vaults](#vaults)** → Credential management for emails, passwords, MFA tokens, credit cards
- **[Digital personas](#personas)** → Identities with their own email, phone number and automated 2FA

> **Coming from notte 1.9 or earlier?** The agent loop (`notte.Agent`, `client.Agent`, `AgentFallback`), workflows and local function execution were removed in 1.10. Coding agents such as Claude Code drive Notte through the [CLI](https://docs.notte.cc/cli), the [MCP server](https://docs.notte.cc/mcp-server) or this SDK instead. If you still need the agent APIs, pin `notte<1.10`.

# Quickstart

For JavaScript and TypeScript, see the [Node SDK](node-sdk/README.md) (`npm install notte-sdk`).

```
pip install notte
patchright install --with-deps chromium
```

## Local sessions

Run a browser on your machine, observe the actions available on a page, execute them and scrape the result. No API key needed:

```python
import notte

with notte.Session(headless=True) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc")
    obs = session.observe()
    print(obs.space.description)
    markdown = session.scrape(only_main_content=True)
```

Structured scraping on a local session hands the page markdown to an extractor. Install the LLM extractor with `pip install 'notte[llm]'` and set `OPENROUTER_API_KEY`; it defaults to `google/gemini-3.5-flash-lite`. You can also pass your own extractor with `notte.Session(extractor=...)`.

Set `OPENROUTER_API_KEY` to use OpenRouter with `google/gemini-3.5-flash-lite` by default.
For another OpenAI-compatible endpoint, set all three of `NOTTE_LLM_BASE_URL`,
`NOTTE_LLM_API_KEY`, and `NOTTE_LLM_MODEL` (the endpoint's own model ID):

- OpenAI: `NOTTE_LLM_BASE_URL=https://api.openai.com/v1`, `NOTTE_LLM_MODEL=gpt-4o`.
- Gemini: `NOTTE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `NOTTE_LLM_MODEL=gemini-3.5-flash-lite`.
- Ollama/custom: `NOTTE_LLM_BASE_URL=http://localhost:11434/v1`, your local model ID, and `NOTTE_LLM_API_KEY=ollama` for an unauthenticated local server. Ollama has not been live-tested.

`NOTTE_LLM_API_KEY` overrides `OPENROUTER_API_KEY`. The latter is used only at the default
OpenRouter URL, so it is never sent to a custom endpoint. The per-call `model=` argument
selects a model at the configured endpoint without translating its ID.

See [notte-llm configuration](packages/notte-llm/README.md) for all settings.

## Cloud sessions

The API hosts the browser sessions for you and adds stealth, CAPTCHA solving, proxies, live view and recordings. Sign up on the [Notte Console](https://console.notte.cc) and create a free Notte API key 🔑

```python
from notte_sdk import NotteClient

client = NotteClient()  # reads NOTTE_API_KEY

with client.Session(open_viewer=False) as session:
    _ = session.execute(type="goto", url="https://news.ycombinator.com")
    actions = session.observe(instructions="open the comments of the first post")
    if actions:
        _ = session.execute(actions[0])
    comments = session.scrape(only_main_content=True)
```

Every cloud session exposes a CDP endpoint, so you can keep your existing Playwright code (`pip install 'notte-sdk[playwright]'`):

```python
from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright

client = NotteClient()

with client.Session(open_viewer=False) as session, sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(session.cdp_url())
    page = browser.contexts[0].pages[0]
    _ = page.goto("https://www.notte.cc")
    print(page.title())
```

# Session features

## Stealth

Built-in proxies, CAPTCHA solving and real Chrome browsers to get through bot detection.

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    solve_captchas=True,
    proxies=True,  # US-based proxy
    browser_type="chrome",
) as session:
    _ = session.execute(type="goto", url="https://www.google.com/recaptcha/api2/demo")
    result = session.execute(type="captcha_solve", captcha_type="recaptcha", raise_on_failure=False)
```

For a custom proxy, set `PROXY_SERVER`, `PROXY_USERNAME`, and `PROXY_PASSWORD` to your provider's connection details.

```python requires-env="PROXY_SERVER,PROXY_USERNAME,PROXY_PASSWORD"
import os
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy

client = NotteClient()
proxy_settings = ExternalProxy(
    server=os.environ["PROXY_SERVER"],
    username=os.environ["PROXY_USERNAME"],
    password=os.environ["PROXY_PASSWORD"],
)

with client.Session(proxies=[proxy_settings]) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc")
```

## File download / upload

Files uploaded to a session can be set on file inputs, and files downloaded by the browser are stored with the session.
Set `UPLOAD_FILE_PATH` to a local document and `UPLOAD_URL` to a page with a file input.

```python requires-env="UPLOAD_FILE_PATH,UPLOAD_URL"
import os
from notte_sdk import NotteClient
from notte_sdk.types import FileSource

client = NotteClient()

with client.Session() as session:
    storage = session.storage
    uploaded_file = storage.upload(os.environ["UPLOAD_FILE_PATH"])

    _ = session.execute(type="goto", url=os.environ["UPLOAD_URL"])
    _ = session.execute(type="upload_file", selector="input[type=file]", file_path=uploaded_file.filename)

    # Download the files the browser downloaded (100 files per page)
    offset = 0
    while True:
        downloaded_files = storage.list(source=FileSource.SESSION_DOWNLOAD, offset=offset)
        for file in downloaded_files.files:
            storage.download(file_id=file.id, local_dir="./results")
        offset += len(downloaded_files.files)
        if offset >= downloaded_files.total or not downloaded_files.files:
            break
```

## Cookies / Auth Sessions

Cookies provide a flexible way to authenticate your sessions. While we recommend using the secure vault for credential management, cookies offer an alternative approach for certain use cases.

```python
from notte_sdk import NotteClient
import json

client = NotteClient()

# Upload cookies for authentication
cookies = [
    {
        "name": "sb-db-auth-token",
        "value": "base64-cookie-value",
        "domain": "github.com",
        "path": "/",
        "expires": 9778363203.913704,
        "httpOnly": False,
        "secure": False,
        "sameSite": "Lax"
    }
]

with client.Session() as session:
    session.set_cookies(cookies=cookies)  # or cookie_file="path/to/cookies.json"
    _ = session.execute(type="goto", url="https://github.com/nottelabs/notte")

    # Get cookies from the session
    cookies_resp = session.get_cookies()
    with open("cookies.json", "w") as f:
        json.dump(cookies_resp, f)
```

## Bring your own browser

Point a session at any CDP-compatible browser (another provider, or a browser you run yourself) to use Notte's observe / execute / scrape on top of it. Set `EXTERNAL_CDP_URL` to the WebSocket URL of a running browser.

```python requires-env="EXTERNAL_CDP_URL"
import os
from notte_sdk import NotteClient

client = NotteClient()
cdp_url = os.environ["EXTERNAL_CDP_URL"]

with client.Session(cdp_url=cdp_url, proxies=False, viewport_width=None, viewport_height=None) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc/pricing")
    pricing = session.scrape(instructions="extract the pricing plans")
```

# Vaults

Store credentials in a vault and let the session fill them in: your code (and the LLMs that write it) only ever sees placeholders. Set `GITHUB_EMAIL` and `GITHUB_PASSWORD` to try it.

```python requires-env="GITHUB_EMAIL,GITHUB_PASSWORD"
import os
from notte import EMAIL, PASSWORD
from notte_sdk import NotteClient

client = NotteClient()

with client.Vault() as vault:
    vault.add_credentials(
        url="https://github.com",
        email=os.environ["GITHUB_EMAIL"],
        password=os.environ["GITHUB_PASSWORD"],
    )
    with client.Session(vault=vault) as session:
        _ = session.execute(type="goto", url="https://github.com/login")
        _ = session.execute(type="form_fill", value={"email": EMAIL, "current_password": PASSWORD})
```

# Personas

Personas are digital identities with a unique email address (and optionally a phone number) whose inbox your automation can read, e.g. for sign-ups and email verification codes.

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Persona(create_phone_number=False) as persona:
    print(f"Sign up with {persona.email}")
    emails = persona.emails(only_unread=True)
```

# Functions

Deploy a Python file with a `run` function and invoke it on the Notte cloud, from the SDK, the API or a schedule. Functions are where your automations, including the ones written by coding agents, run in production.

```python
import tempfile
from notte_sdk import NotteClient

client = NotteClient()

code = '''
from notte_sdk import NotteClient

def run(url: str) -> str:
    client = NotteClient()
    with client.Session() as session:
        _ = session.execute(type="goto", url=url)
        return session.scrape(only_main_content=True)
'''

with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
    _ = f.write(code)

function = client.Function(path=f.name, name="scrape-page")
try:
    result = function.run(url="https://www.notte.cc", stream=False)
    print(result.result)
finally:
    function.delete()
```

# Scraping

For fast data extraction, the scraping endpoint creates and manages the session for you. Pass instructions or a Pydantic model for structured output.

<!-- release-test -->
```python
from notte_sdk import NotteClient
from pydantic import BaseModel

client = NotteClient()

# Simple scraping
response = client.scrape(
    url="https://notte.cc",
    scrape_links=True,
    only_main_content=True
)

# Structured scraping with custom instructions
class Post(BaseModel):
    title: str
    url: str

class Posts(BaseModel):
    posts: list[Post]

response = client.scrape(
    url="https://news.ycombinator.com",
    response_format=Posts,
    instructions="Extract the title and link of the first 5 posts"
)
```

Or directly with cURL
```bash
curl -X POST 'https://api.notte.cc/scrape' \
  -H 'Authorization: Bearer <NOTTE-API-KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://notte.cc",
    "only_main_content": false
  }'
```

# License

This project is licensed under the Server Side Public License v1.
See the [LICENSE](LICENSE) file for details.

# Citation

If you use notte in your research or project, please cite:

```bibtex
@software{notte2025,
  author = {Pinto, Andrea and Giordano, Lucas and {nottelabs-team}},
  title = {Notte: Software suite for internet-native agentic systems},
  url = {https://github.com/nottelabs/notte},
  year = {2025},
  publisher = {GitHub},
  license = {SSPL-1.0}
  version = {2.0.0},
}
```

Copyright © 2025 Notte Labs, Inc.
