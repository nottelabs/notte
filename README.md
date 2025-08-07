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

Notte provides all the essential tools for building and deploying AI agents that interact seamlessly with the web. Our full-stack web AI agents framework allows you to develop, deploy, and scale your own agents and web automations, all with a single API. Read more in our documentation [here](https://docs.notte.cc) 🔥

### Key features

Opensource:
- **[Run web agents](https://docs.notte.cc/concepts/agents)** → task an AI agent from a single prompt
- **[Site interactions](https://docs.notte.cc/concepts/sessions#operations)** → observe website states, scrape data and execute actions using simple Playwright compatible primitives and intuitive natural language commands

API service:
- **[Stealth Browser Sessions](https://docs.notte.cc/concepts/sessions)** → on-demand headless browser instances (Chrome, Firefox, Chromium), built in & custom proxy config, CDP compatible, cookie integration, session replay, automated captcha solving
- **[Secrets Vaults](https://docs.notte.cc/concepts/vaults)** → enterprise-grade 
credential management to securely store emails, passwords, MFA tokens, SSO, etc.
- **[Personas](https://docs.notte.cc/concepts/personas)** → self-service digital identities with unique email addresses, phone numbers, 2FA handling for seamless account creation and authentication workflows

# Quickstart

```
pip install notte
patchright install --with-deps chromium
```

### Run in local mode

Use the following script to spinup an agent using opensource features (you need your own LLM API keys):

```python
import notte
from dotenv import load_dotenv
load_dotenv()

with notte.Session(headless=False) as session:
    agent = notte.Agent(session=session, reasoning_model='gemini/gemini-2.5-flash', max_steps=30)
    response = agent.run(task="doom scroll cat memes on google images")
```

### Using Python SDK

We also provide an effortless API that hosts the browser sessions for you - and provide plenty of premium features. To run the agent you'll need to first sign up on the [Notte Console](https://console.notte.cc) and create a free Notte API key 🔑

```python
from notte_sdk import NotteClient

cli = NotteClient(api_key="your-api-key")

with cli.Session(headless=False) as session:
    agent = cli.Agent(session=session, reasoning_model='gemini/gemini-2.5-flash', max_steps=30)
    response = agent.run(task="doom scroll cat memes on google images")
```

# Benchmarks

| Rank | Provider                                                    | Agent Self-Report | LLM Evaluation | Time per Task | Task Reliability |
| ---- | ----------------------------------------------------------- | ----------------- | -------------- | ------------- | ---------------- |
| 🏆   | [Notte](https://github.com/nottelabs/notte)                 | **86.2%**         | **79.0%**      | **47s**       | **96.6%**        |
| 2️⃣   | [Browser-Use](https://github.com/browser-use/browser-use)   | 77.3%             | 60.2%          | 113s          | 83.3%            |
| 3️⃣   | [Convergence](https://github.com/convergence-ai/proxy-lite) | 38.4%             | 31.4%          | 83s           | 50%              |

Read the full story here: [https://github.com/nottelabs/open-operator-evals](https://github.com/nottelabs/open-operator-evals)

# Scraping
We also have a specialized scraping endpoint:
```bash
curl -X POST \
  'https://api.notte.cc/scrape' \
  -H 'Authorization: Bearer <NOTTE-API-KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
        "url": "https://notte.cc",
        "scrape_links": true,
        "only_main_content": false,
        "scrape_images": false,
      }'
```
Read more about parameters in the docs page: https://docs.notte.cc/api-reference/scrape/scrape-webpage 

# 🔥 Build Powerful Web Agents

Notte is composed of 3 main components that can be combined to build your own agentic system: `notte.Session`, `notte.Vault` and `notte.Agent`.

You can use the `notte.Session` to create a browser session with different stealth configurations (i.e browser types, proxies, captcha, etc), the `notte.Vault` to store your credentials and the `notte.Agent` to run your agent.

Here is an example of how to use these components together along with structured output:

```python
from notte_sdk import NotteClient
from pydantic import BaseModel

class TwitterPost(BaseModel):
    url: str

notte = NotteClient()
with notte.Vault() as vault, notte.Session(headless=False, proxies=False, browser_type="chrome") as session:
    vault.add_credentials(
        url="https://x.com",
        username="your-email",
        password="your-password",
    )
    agent = notte.Agent(session=session, vault=vault, max_steps=10)
    response = agent.run(
      task="go to twitter and post: new era this is @nottecore taking over my acc. Return the post url.",
      response_format=TwitterPost,
    )
print(response.answer)
```

# Demos

<p align="center">
  <img src="docs/gifs/v1.gif" alt="Demo" width="100%" href="https://video.twimg.com/ext_tw_video/1892967963344461824/pu/vid/avc1/1282x720/15sCfmmUUcAtBZaR.mp4">
</p>

# A full stack framework

### Highlights ✨

We introduce a perception layer that transforms websites into structured, natural-language maps. This reduces parsing complexity, making it easier for LLMs to understand and act on web content.

The result: lower cognitive load, better accuracy, and support for smaller, faster models—cutting both inference time and production costs.

Notte's full stack agentic internet framework combines core browser infrastructure (sessions, live replay, cdp) with intelligent browsing agents, bridged and enhanced with our perception layer. Our entire codebase is made to be highly customizable, ready to integrate other devtools from the ecosystem and packaged to be push to prod. We also provide web scripting capabilities and sota scraping endpoints out of the box, because why not.

### Unstable and upcoming features

⏭️ We have either already partially shipped or are working on the following features: captcha resolution, residential proxies, web security, vpn-style browsing, authentication and payments with secure safe, improved speed and memory, human-in-the-loop integration, channeled notifications, and cookies management.

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
