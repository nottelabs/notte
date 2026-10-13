# Rapidly build reliable web automation agents

<div align="center">
  <p>
    The web agent framework built for <strong>speed</strong>, <strong>cost-efficiency</strong>, <strong>scale</strong>, and <strong>reliability</strong> <br/>
    → <a href="https://docs.notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Docs</a> • <a href="https://console.notte.cc/?ref=github" target="_blank" rel="noopener noreferrer">Console</a> • <a href="https://anything.notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Anything API</a> • <a href="https://notte.cc?ref=github" target="_blank" rel="noopener noreferrer">Landing</a> • <a href="https://join.slack.com/t/nottelabs-dev/shared_invite/zt-39a8n6hr9-d_BG7RNfytimSpVo5H03mA" target="_blank" rel="noopener noreferrer">Slack</a> • <a href="https://x.com/nottecore?ref=github" target="_blank" rel="noopener noreferrer">X</a>
  </p>
</div>

<p align="center">
  <img src="docs/logo/bgd.png" alt="Notte Logo" width="100%">
</p>

[![GitHub stars](https://img.shields.io/github/stars/nottelabs/notte?style=social)](https://github.com/nottelabs/notte/stargazers)
[![License: SSPL-1.0](https://img.shields.io/badge/License-SSPL%201.0-blue.svg)](LICENSE)
[![PyPI Downloads](https://static.pepy.tech/badge/notte?color=blue)](https://pepy.tech/projects/notte)
[![npm version](https://img.shields.io/npm/v/notte-sdk?color=blue)](https://www.npmjs.com/package/notte-sdk)

---

Notte gives AI agents and automation scripts a browser. Script the deterministic parts, use AI only where you need it, and run it all on stealth cloud browsers with a single API.

```bash
pip install notte-sdk        # or: npm install notte-sdk
```

## Quickstart

Create a free API key in the [Console](https://console.notte.cc) 🔑, then:

```python
from notte_sdk import NotteClient
from pydantic import BaseModel


class Post(BaseModel):
    title: str
    points: int


class TopPosts(BaseModel):
    posts: list[Post]


client = NotteClient()  # reads NOTTE_API_KEY

with client.Session(open_viewer=True) as session:  # stealth cloud browser + live view
    agent = client.Agent(session=session, max_steps=10)
    response = agent.run(
        task="Go to news.ycombinator.com and return the top 3 posts",
        response_format=TopPosts,
    )

print(response.answer)
```

<details>
<summary><b>TypeScript</b></summary>

```typescript
import { NotteClient } from 'notte-sdk';

const client = new NotteClient(); // reads NOTTE_API_KEY

await client.Session({ open_viewer: true }).use(async (session) => {
  const agent = client.Agent({ session, max_steps: 10 });
  const response = await agent.run({ task: 'Go to news.ycombinator.com and return the top 3 posts' });
  console.log(response.answer);
});
```

</details>

<details>
<summary><b>Let your coding agent set it up</b></summary>

Paste this into Claude Code, Codex or Cursor. It installs the Notte skill and CLI, signs you in and opens a live session:

```text
Read https://notte.cc/skill.md and follow its setup instructions.
```

</details>

## Which Notte do I need?

| You want to... | Use |
|---|---|
| Give Claude, Codex or Cursor a browser | [Browser MCP](#give-your-coding-agent-a-browser) |
| Describe a task in English and get the result | [Agents](#quickstart) |
| Run your own Playwright / Puppeteer code on stealth cloud browsers | [Sessions](#sessions-bring-your-own-playwright) |
| Mix scripted steps with agents | [Hybrid workflows](#hybrid-workflows) |
| Ship a browser script as an API endpoint or a cron job | [Functions](#functions) |
| Describe a task in English and get a deployed API back | [Anything API](#anything-api) |
| Turn a URL into structured data | [Scraping](#scraping) |
| Drive browsers from the terminal or CI | [notte-cli](https://github.com/nottelabs/notte-cli) |

## Give your coding agent a browser

```bash
claude mcp add --transport http notte https://api.notte.cc/mcp
npx skills add nottelabs/notte-skills -y    # optional: Notte agent skills
```

Run `/mcp` in Claude Code to sign in. Setup for Codex, Cursor and other clients is in the [MCP docs](https://docs.notte.cc/mcp-server).

## Sessions: bring your own Playwright

Every session is a cloud Chrome with proxies, CAPTCHA solving, anti-detection, live view and recordings. Connect anything that speaks CDP: Playwright, Puppeteer, Stagehand, Browser Use.

```python
from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright

client = NotteClient()

with client.Session(proxies=True, solve_captchas=True) as session:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(session.cdp_url())
        page = browser.contexts[0].pages[0]
        page.goto("https://example.com")
        print(page.title())
```

For logged-in workflows, attach a [Vault](https://docs.notte.cc/concepts/vaults) (credentials and MFA the LLM never sees), a [Browser Profile](https://docs.notte.cc/features/sessions/browser-profiles) or a [Persona](https://docs.notte.cc/concepts/personas).

## Hybrid workflows

Script the deterministic steps, hand the rest to an agent. Faster, cheaper and more reliable than running an agent end to end.

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(open_viewer=True) as session:
    session.execute(type="goto", url="https://github.com/nottelabs")  # scripted
    agent = client.Agent(session=session, max_steps=10)  # reasoning
    response = agent.run(task="Open the notte repository owned by nottelabs. Finish on its repository home page.")
    data = session.scrape(instructions="Extract number of stars")  # extraction
```

**Agent fallback.** Scripts break when sites change. Wrap scripted steps in an `AgentFallback` and an agent takes over when a step fails:

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://shop.notte.cc/")
    with client.AgentFallback(session=session, task="Go to the cart page") as agent:
        session.execute(type="click", selector="#this-button-does-not-exist")  # fails -> agent recovers
```

## Functions

Deploy a script as a serverless endpoint. Call it over HTTP, schedule it with cron, or trigger it from your app.

```python requires-env="NOTTE_FUNCTION_ID"
import os

from notte_sdk import NotteClient

client = NotteClient()

# Deploy once with: client.Function(path="my_automation.py", name="My automation")
function = client.Function(function_id=os.environ["NOTTE_FUNCTION_ID"])
result = function.run(url="https://example.com")
print(result.result)
```

## Anything API

Describe a web task in English. Notte explores the site, writes the automation, deploys it as a Function and runs it.

```bash
curl -N -X POST https://anything.notte.cc/api/anything/start \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "fetch the top 3 hacker news posts"}'
```

Or browse ready-made functions in the [marketplace](https://anything.notte.cc/marketplace).

## Scraping

One call, no session to manage. Get markdown, or data in your schema.

```python
from notte_sdk import NotteClient
from pydantic import BaseModel


class Article(BaseModel):
    title: str
    content: str


client = NotteClient()
article = client.scrape(url="https://example.com", response_format=Article)
print(article)
```

## Open source or Notte Cloud

This repo contains the open source agent framework (`notte`) and the cloud SDKs (`notte-sdk` for Python, `notte-sdk` on npm).

| | Open source | Notte Cloud |
|---|---|---|
| Install | `pip install notte` | `pip install notte-sdk` |
| Browser | Local Chromium | Managed cloud Chrome |
| LLM | Your own keys | Notte-managed or your own keys |
| Proxies, CAPTCHA, anti-detection | Bring your own | Built in |
| Vaults, profiles, personas | - | Built in |
| Functions, Anything API, Browser MCP | - | Built in |

<details>
<summary><b>Run the open source agent locally</b></summary>

```bash
pip install notte
patchright install --with-deps chromium
```

```python
import notte
import os

with notte.Session(headless=False) as session:
    model = os.getenv("NOTTE_EXAMPLE_MODEL", "gemini/gemini-3.5-flash")
    agent = notte.Agent(session=session, reasoning_model=model, max_steps=10)
    response = agent.run(task="Find three cat memes on Google Images and describe them")
```

</details>

## Resources

- [Documentation](https://docs.notte.cc) · [llms.txt](https://docs.notte.cc/llms.txt) for AI agents
- [Node SDK](node-sdk/README.md) · [API reference](https://docs.notte.cc/api-reference/authentication) · [Pricing](https://www.notte.cc/pricing)
- [BrowserArena](https://browserarena.ai): our open benchmark of cloud browser providers
- [Contributing](docs/CONTRIBUTING.md)

## License

This project is licensed under the [Server Side Public License v1](LICENSE).

<details>
<summary><b>Citation</b></summary>

```bibtex
@software{notte2025,
  author = {Pinto, Andrea and Giordano, Lucas and {nottelabs-team}},
  title = {Notte: Software suite for internet-native agentic systems},
  url = {https://github.com/nottelabs/notte},
  year = {2025},
  publisher = {GitHub},
  license = {SSPL-1.0},
}
```

</details>

Copyright © 2025-2026 Notte Labs, Inc.
