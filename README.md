[![GitHub stars](https://img.shields.io/github/stars/nottelabs/notte?style=social)](https://github.com/nottelabs/notte/stargazers)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PyPI version](https://img.shields.io/pypi/v/notte)](https://pypi.org/project/notte/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/discord/1312234428444966924?color=7289DA&label=Discord&logo=discord&logoColor=white)](https://discord.gg/atbh5s6bts)

# Notte 🌌

**Notte is a web browser for LLM agents.** It transforms the internet into an agent-friendly environment, turning websites into structured, navigable maps described in natural language. By using natural language commands, Notte minimizes hallucinations, reduces token usage, and lowers costs and latency. It handles the browser complexity so your LLM policies can focus on what they do best: conversational reasoning and planning.

## A new paradigm for web agent navigation:

- Language-first web navigation, no DOM/HTML parsing required
- Treats the web as a structured, natural language action map
- Reinforcement learning style action space and controls

# Install

Requires Python 3.11+

```bash
pip install notte
playwright install
```

# Config

Notte uses language models to parse and structure web pages into a structured action space. To get started, you need to provide at least one API key for a supported language model provider. These keys can be configured in `.env` file and loaded into your environment;

```python
os.environ["OPENAI_API_KEY"] = "your-api-key"
# or any other provider(s) you have keys for
```

### Supported default providers

By default, Notte supports the following providers:

- [Cerebras](https://console.anthropic.com/) fastest, 60K tpm rate limit, wait-list keys
- [Anthropic](https://docs.anthropic.com/en/docs/api/api-reference) 40K tpm rate limit
- [OpenAI](https://platform.openai.com/docs/guides/chat/introduction) 30k tpm rate limit
- [Groq](https://groq.com/llm-api) fast, 6K tpm rate limit

# Usage

As a reinforcement learning environment to get full control;

```python
from notte.env import NotteEnv

# setting fast language model provider keys
os.environ['CEREBRAS_API_KEY'] = "your-api-key"

async with NotteEnv(headless=False) as env:
  # observe a webpage, and take a random action
  obs = await env.observe("https://www.google.com/travel/flights")
  obs = await env.step(obs.space.sample().id)
```

The observation object contains all you need about the current state of a page;

```bash
> obs = env.observe("https://www.google.com/travel/flights")
> print(obs.actions.markdown())

# Flight Search
* I1: Enters departure location (departureLocation: str = "San Francisco")
* I2: Enters destination location (destinationLocation: str)
* I3: Selects departure date (departureDate: date)
* I4: Selects return date (returnDate: date)
* I5: Selects seating class (seatClass: str = "Economy", allowed=["Economy", "Premium Economy", "Business", "First"])
* I6: Selects trip type (tripType: str = "round-trip", allowed=["round-trip", "one-way", "multi-city"])
* B1: Open menu to change number of passengers
* B2: Swaps origin and destination locations
* B3: Search flights options with current filters

# Website Navigation
* B5: Opens Google apps menu
* L28: Navigates to Google homepage
* L29: Navigates to Hotels section

# User Preferences
* B26: Open menu to change language settings
* B27: Open menu to change location settings
* B28: Open menu to change currency settings

# Destination Exploration
* L1: Shows flights from London to Tokyo
* L2: Shows flights from New York to Rome
[... More actions/categories ...]
```

## As a backend for LLM web agents

Or alternatively, you can use Notte conversationally with an LLM agent:

```python
from notte.env import NotteEnv
import litellm

goal = "Find best flights from Boston to Tokyo"
messages = [{"role": "system", "content": goal}]
max_steps = 10

def llm_agent(messages):
    response = litellm.completion(
        model="gpt-4o",
        messages=messages,
    )
    return response.choices[0].message.content

async def main(max_steps=10):
  async with NotteEnv(headless=False) as env:
    while '<done>' not in messages[-1]['content'] and max_steps > 0:
      resp = llm_agent(messages) # query your llm policy.
      obs = await env.chat(resp) # query notte with llm response.
      messages.append({"role": "assistant", "content": resp})
      messages.append({"role": "user", "content": obs})
      max_steps -= 1

import asyncio
asyncio.run(main())
```

🌌 Use Notte as a backend environment for a web-based LLM agent. In this example, you integrate your own LLM policy, manage the interaction flow, handle errors, and define rewards, all while letting Notte handle webpages parsing/understanding and browser interactions.

# API services

We offer managed cloud browser sessions with the following premium add-ons:

- **Authentication:** Built-in auth for secure workflows.
- **Caching:** Fast responses with intelligent caching.
- **Action Permissions:** Control over sensitive actions.

Request access to a set of API keys on [notte.cc](https://notte.cc)

Then integrate with a single line drop-in;

```python
from notte.sdk import NotteClient
env = NotteClient(api_key="your-api-key")
```

# Main features

- **Web Driver Support:** Compatible with any web driver. Defaults to Playwright.
- **LLM Integration:** Use any LLM as a policy engine with quick prompt tuning.
- **Multi-Step Actions**: Navigate and act across multiple steps.
- **Extensible:** Simple to integrate and customize.

# Advanced Config

### Using multiple keys

If you supply multiple keys in your `.env` file, Notte uses a [llamux](https://github.com/andreakiro/llamux-llm-router) configuration to intelligently select the best model for each invocation. This approach helps avoid rate limits, optimize cost-performance balance, and enhance your experience. You can add more providers or adjust rate limits by modifying the [config file](notte/llms/config/endpoints.csv)

# Contribute

Setup your local working environment;

```bash
poetry env use 3.11 && poetry shell
poetry install --with dev
poetry run playwright install
pre-commit install
```

Find an issue, fork, open a PR, and merge :)

# License

Notte is released under the [Apache 2.0 license](LICENSE)
