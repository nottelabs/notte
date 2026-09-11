# Rapidly build reliable web automation agents

<div align="center">
  <p>
    The web agent framework built for <strong>speed</strong>, <strong>cost-efficiency</strong>, <strong>scale</strong>, and <strong>reliability</strong> <br/>
    → Read more at: <a href="https://github.com/nottelabs/open-operator-evals" target="_blank" rel="noopener noreferrer">open-operator-evals</a> • <a href="https://x.com/nottecore?ref=github" target="_blank" rel="noopener noreferrer">X</a> • <a href="https://www.linkedin.com/company/nottelabsinc/?ref=github" target="_blank" rel="noopener noreferrer">LinkedIn</a> • <a href="https://notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Landing</a> • <a href="https://console.notte.cc/?ref=github" target="_blank" rel="noopener noreferrer">Console</a>
  </p>
</div>

<p align="center">
  <img src="docs/logo/bgd.png" alt="Notte Logo" width="100%">
</p>

[![GitHub stars](https://img.shields.io/github/stars/nottelabs/notte?style=social)](https://github.com/nottelabs/notte/stargazers)
[![License: SSPL-1.0](https://img.shields.io/badge/License-SSPL%201.0-blue.svg)](https://spdx.org/licenses/SSPL-1.0.html)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/notte?color=blue)](https://pypi.org/project/notte/)
[![PyPI Downloads](https://static.pepy.tech/badge/notte?color=blue)](https://pepy.tech/projects/notte)

---

# What is Notte?

Notte provides all the essential tools for building and deploying AI agents that interact seamlessly with the web. Our full-stack framework combines AI agents with traditional scripting for maximum efficiency - letting you script deterministic parts and use AI only when needed, cutting costs by 50%+ while improving reliability. We allow you to develop, deploy, and scale your own agents and web automations, all with a single API. Read more in our documentation [here](https://docs.notte.cc) 🔥

**Opensource Core:**
- **[Run web agents](#using-python-sdk-recommended)** → Give AI agents natural language tasks to complete on websites
- **[Structured Output](#structured-output)** → Get data in your exact format with Pydantic models
- **[Site Interactions](#scraping)** → Observe website states, scrape data and execute actions using Playwright compatible primitives and natural language commands

**API service (Recommended)**
- **[Stealth Browser Sessions](#session-features)** → Browser instances with built-in CAPTCHA solving, proxies, and anti-detection
- **[Hybrid Workflows](#workflows)** → Combine scripting and AI agents to reduce costs and improve reliability
- **[Secrets Vaults](#agent-vault)** → Enterprise-grade credential management to store emails, passwords, MFA tokens, SSO, etc.
- **[Digital Personas](#agent-persona)** → Create digital identities with unique emails, phones, and automated 2FA for account creation workflows

# Quickstart

For JavaScript and TypeScript, see the [Node SDK](node-sdk/README.md) (`npm install notte-sdk`).

```
pip install notte
patchright install --with-deps chromium
```

### Run in local mode

Use the following script to spinup an agent using opensource features (you'll need your own LLM API keys):

```python
import notte
import os
from dotenv import load_dotenv
load_dotenv()

with notte.Session(headless=False) as session:
    model = os.getenv("NOTTE_EXAMPLE_MODEL", "gemini/gemini-2.5-flash")
    agent = notte.Agent(session=session, reasoning_model=model, max_steps=10)
    response = agent.run(task="Find three cat memes on Google Images and describe them")
```

### Using Python SDK (Recommended)

We also provide an effortless API that hosts the browser sessions for you - and provide plenty of premium features. To run the agent you'll need to first sign up on the [Notte Console](https://console.notte.cc) and create a free Notte API key 🔑

```python
from notte_sdk import NotteClient
import os

client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

with client.Session(open_viewer=True) as session:
    agent = client.Agent(session=session, reasoning_model='gemini/gemini-2.5-flash', max_steps=30)
    response = agent.run(task="doom scroll cat memes on google images")
```

Our setup allows you to experiment locally, then drop-in replace the import and prefix `notte` objects with `cli` to switch to SDK and get hosted browser sessions plus access to premium features!

# Benchmarks

| Rank | Provider                                                    | Agent Self-Report | LLM Evaluation | Time per Task | Task Reliability |
| ---- | ----------------------------------------------------------- | ----------------- | -------------- | ------------- | ---------------- |
| 🏆   | [Notte](https://github.com/nottelabs/notte)                 | **86.2%**         | **79.0%**      | **47s**       | **96.6%**        |
| 2️⃣   | [Browser-Use](https://github.com/browser-use/browser-use)   | 77.3%             | 60.2%          | 113s          | 83.3%            |
| 3️⃣   | [Convergence](https://github.com/convergence-ai/proxy-lite) | 38.4%             | 31.4%          | 83s           | 50%              |

Read the full story here: [https://github.com/nottelabs/open-operator-evals](https://github.com/nottelabs/open-operator-evals)

# Agent features

## Structured output

Structured output is a feature of the agent's run function that allows you to specify a Pydantic model as the `response_format` parameter. The agent will return data in the specified structure.

```python
from notte_sdk import NotteClient
from pydantic import BaseModel

class HackerNewsPost(BaseModel):
    title: str
    url: str
    points: int
    author: str
    comments_count: int

class TopPosts(BaseModel):
    posts: list[HackerNewsPost]

client = NotteClient()
with client.Session(open_viewer=True, browser_type="chrome") as session:
    agent = client.Agent(session=session, reasoning_model='gemini/gemini-2.5-flash', max_steps=15)
    response = agent.run(
        task="Go to Hacker News (news.ycombinator.com) and extract the top 5 posts with their titles, URLs, points, authors, and comment counts.",
        response_format=TopPosts,
    )
print(response.answer)
```

## Agent vault
Vaults are tools you can attach to your Agent instance to securely store and manage credentials. The agent automatically uses these credentials when needed.

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Vault() as vault, client.Session(open_viewer=True) as session:
    vault.add_credentials(
        url="https://x.com",
        username="your-email",
        password="your-password",
    )
    agent = client.Agent(session=session, vault=vault, max_steps=10)
    response = agent.run(
      task="go to twitter; login and go to my messages",
    )
print(response.answer)
```

## Agent persona

Personas are tools you can attach to your Agent instance to provide digital identities with unique email addresses, phone numbers, and automated 2FA handling.

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Persona(create_phone_number=False) as persona:
    with client.Session(browser_type="chrome", open_viewer=True) as session:
        agent = client.Agent(session=session, persona=persona, max_steps=15)
        response = agent.run(
            task="Open the Google form and RSVP yes with your name",
            url="https://forms.google.com/your-form-url",
        )
print(response.answer)
```

# Session features

## Stealth

Stealth features include automatic CAPTCHA solving and proxy configuration to enhance automation reliability and anonymity.

```python
from notte_sdk import NotteClient

client = NotteClient()

# Built-in proxies with CAPTCHA solving
with client.Session(
    solve_captchas=True,
    proxies=True,  # US-based proxy
    browser_type="chrome",
    open_viewer=True
) as session:
    agent = client.Agent(session=session, max_steps=5)
    response = agent.run(
        task="Try to solve the CAPTCHA using internal tools",
        url="https://www.google.com/recaptcha/api2/demo"
    )

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
    agent = client.Agent(session=session, max_steps=5)
    response = agent.run(task="Navigate to a website")
```

## File download / upload

File Storage allows you to upload files for your agents and download files that agents retrieve during their work.
Both uploaded files and browser downloads belong to a session. Start a session before uploading files, and use file IDs to download them.
Set `UPLOAD_FILE_PATH` to a local document and `UPLOAD_URL` to the website where your agent should upload it.

```python requires-env="UPLOAD_FILE_PATH,UPLOAD_URL"
import os
from notte_sdk import NotteClient
from notte_sdk.types import FileSource

client = NotteClient()

with client.Session() as session:
    storage = session.storage
    uploaded_file = storage.upload(os.environ["UPLOAD_FILE_PATH"])
    storage.download(file_id=uploaded_file.id, local_dir="./inputs")

    agent = client.Agent(session=session, max_steps=5)
    response = agent.run(
        task=f"Upload {uploaded_file.filename} to the website and download the cat picture",
        url=os.environ["UPLOAD_URL"],
    )

    # Download files that the agent downloaded (100 files per page)
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
    
    agent = client.Agent(session=session, max_steps=5)
    response = agent.run(
        task="go to nottelabs/notte get repo info",
    )
    
    # Get cookies from the session
    cookies_resp = session.get_cookies()
    with open("cookies.json", "w") as f:
        json.dump(cookies_resp, f)
```

## CDP Browser compatibility

You can plug in any browser session provider you want and use our agent on top. Use external headless browser providers via CDP to benefit from Notte's agentic capabilities with any CDP-compatible browser.

Set `EXTERNAL_CDP_URL` to the WebSocket URL of a running browser from your provider.

```python requires-env="EXTERNAL_CDP_URL"
import os
from notte_sdk import NotteClient

client = NotteClient()
cdp_url = os.environ["EXTERNAL_CDP_URL"]

with client.Session(cdp_url=cdp_url, proxies=False, viewport_width=None, viewport_height=None) as session:
    agent = client.Agent(session=session)
    response = agent.run(task="extract pricing plans from https://www.notte.cc/")
```

# Hybrid workflows

Notte's close compatibility with Playwright allows you to mix web automation primitives with agents for specific parts that require reasoning and adaptability. This hybrid approach cuts LLM costs and is much faster by using scripting for deterministic parts and agents only when needed.

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(open_viewer=True) as session:
    # Start with a deterministic navigation
    session.execute(type="goto", url="https://github.com/nottelabs")
    agent = client.Agent(session=session, max_steps=10)
    # Use an agent to reason about the next step
    response = agent.run(task="Open the notte repository owned by nottelabs. Finish on its repository home page.")
    assert response.success, response.answer
    assert session.observe().metadata.url.split("?")[0].rstrip("/") == "https://github.com/nottelabs/notte"
    # Use a scraping endpoint to extract data
    data = session.scrape(instructions="Extract number of stars")
```

# Agent fallback

Workflows are a powerful way to combine scripting and agents to reduce costs and improve reliability. However, deterministic parts of the workflow can still fail. To gracefully handle these failures with agents, you can use the `AgentFallback` class: 

```python
import notte

with notte.Session() as session:
    _ = session.execute(type="goto", url="https://shop.notte.cc/")
    _ = session.observe()

    with notte.AgentFallback(session, "Go to cart"):
        # Force execution failure -> trigger an agent fallback to gracefully fix the issue
        res = session.execute(type="click", id="INVALID_ACTION_ID")
```

# Scraping

For fast data extraction, we provide a dedicated scraping endpoint that automatically creates and manages sessions. You can pass custom instructions for structured outputs and enable stealth mode.

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
class Article(BaseModel):
    title: str
    content: str
    date: str

response = client.scrape(
    url="https://example.com/blog",
    response_format=Article,
    instructions="Extract only the title, date and content of the articles"
)
```

Or directly with cURL
```bash
curl -X POST 'https://api.notte.cc/scrape' \
  -H 'Authorization: Bearer <NOTTE-API-KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://notte.cc",
    "only_main_content": false,
  }'
```


**Search:** We've built a cool demo of an LLM leveraging the scraping endpoint in an MCP server to make real-time search in an LLM chatbot - works like a charm! Available here: [https://search.notte.cc/](https://search.notte.cc/)

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
  version = {1.4.4},
}
```

Copyright © 2025 Notte Labs, Inc.
