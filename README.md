[![GitHub stars](https://img.shields.io/github/stars/nottelabs/notte?style=social)](https://github.com/nottelabs/notte/stargazers)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/discord/1312234428444966924?color=7289DA&label=Discord&logo=discord&logoColor=white)](https://discord.gg/atbh5s6bts)

# Notte 🌌

**Notte is a web browser for LLM agents.** It transforms the internet into an agent-friendly environment, turning websites into structured, navigable maps described in natural language. By using natural language commands, Notte minimizes hallucinations, reduces token usage, and lowers costs and latency. It handles the browser complexity so your LLM policies can focus on what they do best: conversational reasoning and planning.

## A new paradigm for web agent navigation:
- Language-first web navigation, no DOM/HTML parsing required
- Treats the web as a structured, natural language action map
- Reinforcement learning style action space and controls

# Install

Requires Python 3.11+ easy peasy.

```bash
pip install notte
```

# Usage

As a reinforcement learning environment to get full control;

```python
from notte.env import NotteEnv
model = "groq/llama-3.3-70b-versatile"
async with NotteEnv(model=model, headless=False) as env:
  # observe a webpage, and take a random action
  obs = await env.observe("https://www.google.com/travel/flights")
  obs = await env.step(obs.actions.sample().id)
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

# Destination Exploration
* L1: Shows flights from London to Tokyo
* L2: Shows flights from New York to Rome
* [... More actions ...]

# Website Navigation
* B5: Opens Google apps menu
* L28: Navigates to Google homepage
* L29: Navigates to Hotels section

# User Preferences
* B26: Open menu to change language settings
* B27: Open menu to change location settings
* B28: Open menu to change currency settings

[... More actions/categories ...]
```

Or alternatively, you can use Notte conversationally with an LLM agent:

```python
from notte.env import NotteEnv
import litellm

goal = "Find best flights from Boston to Tokyo"
messages = [{"role": "system", "content": goal}]
max_steps = 10

def llm_agent(messages):
    response = litellm.completion(
        model="gpt-4o-mini",
        messages=messages,
    )
    return response.choices[0].message.content

async with NotteEnv(headless=False) as env:
  while '<done>' not in messages[-1]['content'] and max_steps > 0:

    resp = llm_agent(messages) # query your llm policy.
    obs = await env.chat(resp) # query notte with llm response.

    messages.append({"role": "assistant", "content": resp})
    messages.append({"role": "user", "content": obs})
    max_steps -= 1
```

👷🏻‍♂️ See how to create your own advanced agent with Notte in [examples](#examples)!

## Main features

- **Web Driver Support:** Compatible with any web driver. Defaults to Playwright.
- **LLM Integration:** Use any LLM as a policy engine with quick prompt tuning.
- **Multi-Step Actions**: Navigate and act across multiple steps.
- **Extensible:** Simple to integrate and customize.

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

# Examples

1. [Drop-in your own agent super easy](examples/agent.py)

# How to Contribute

Check out the [contributing docs](docs/CONTRIBUTING.md) file for more information on how to contribute to Notte.

# License

Notte is released under the [Apache 2.0 license](LICENSE)
