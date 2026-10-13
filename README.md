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

Notte gives AI agents and developers cloud browsers. Drive them from your terminal, your coding agent or your code, deploy browser automations as APIs, and fetch structured data from any page.

Create a free API key in the [Console](https://console.notte.cc) 🔑, then pick where to start:

| You want to... | Use |
|---|---|
| Drive browsers from the terminal, scripts or CI | [Notte CLI](#notte-cli) |
| Give Claude Code, Codex or Cursor a browser | [Notte MCP](#notte-mcp) |
| Run your own Playwright / Puppeteer code on stealth cloud browsers | [Browser Sessions](#browser-sessions) |
| Ship a browser script as an API endpoint or a cron job | [Browser Functions](#browser-functions) |
| Describe a task in English and get a deployed API back | [Anything API](#anything-api) |
| Turn a URL into clean, structured data | [Fetch](#fetch) |

## Notte CLI

Drive cloud browsers from your terminal, shell scripts or CI.

```bash
brew tap nottelabs/notte-cli https://github.com/nottelabs/notte-cli.git
brew install notte
notte auth login
notte sessions start
notte page goto "https://news.ycombinator.com"
notte page scrape --instructions "Top 3 posts with their points"
notte sessions stop
```

See the [CLI repo](https://github.com/nottelabs/notte-cli) for every command.

<details>
<summary><b>Let your coding agent set it up</b></summary>

Paste this into Claude Code, Codex or Cursor. It installs the Notte skill and CLI, signs you in and opens a live session:

```text
Read https://notte.cc/skill.md and follow its setup instructions.
```

</details>

## Notte MCP

Give your coding agent a cloud browser it can open, drive, observe and scrape, with saved logins.

```bash
claude mcp add --transport http notte https://api.notte.cc/mcp
npx skills add nottelabs/notte-skills -y    # optional: Notte agent skills
```

Run `/mcp` in Claude Code to sign in. Setup for Codex, Cursor and other clients is in the [MCP docs](https://docs.notte.cc/mcp-server).

## Browser Sessions

Every session is a cloud Chrome with proxies, CAPTCHA solving, anti-detection, live view and recordings. Connect anything that speaks CDP: Playwright, Puppeteer, Stagehand, Browser Use.

```bash
pip install notte-sdk        # or: npm install notte-sdk playwright-core
```

```python
from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright

client = NotteClient()  # reads NOTTE_API_KEY

with client.Session(proxies=True, solve_captchas=True) as session:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(session.cdp_url())
        page = browser.contexts[0].pages[0]
        page.goto("https://example.com")
        print(page.title())
```

<details>
<summary><b>TypeScript</b></summary>

```typescript
import { chromium } from 'playwright-core';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient(); // reads NOTTE_API_KEY

await client.Session({ proxies: true, solve_captchas: true }).use(async (session) => {
  const { cdp_url } = await session.status();
  if (!cdp_url) throw new Error('Session did not return a cdp_url');
  const browser = await chromium.connectOverCDP(cdp_url);
  try {
    const page = browser.contexts()[0].pages()[0];
    await page.goto('https://example.com');
    console.log(await page.title());
  } finally {
    await browser.close();
  }
});
```

</details>

For logged-in workflows, attach a [Vault](https://docs.notte.cc/concepts/vaults) (credentials and MFA the LLM never sees), a [Browser Profile](https://docs.notte.cc/features/sessions/browser-profiles) or a [Persona](https://docs.notte.cc/concepts/personas).

## Browser Functions

Deploy a browser script as a serverless endpoint. Call it over HTTP, schedule it with cron, or trigger it from your app.

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

## Fetch

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
