<div align="center">
  <p>
    ⚡️ we outperform other web agents in speed, costs and reliability 👉🏼 <a href="https://github.com/nottelabs/open-operator-evals">read more on open-operator-evals</a>
  </p>
</div>

<p align="center">
  <img src="docs/logo/bgd.png" alt="Notte Logo" width="100%">
</p>

## The full stack for the agentic internet layer

[![GitHub stars](https://img.shields.io/github/stars/nottelabs/notte?style=social)](https://github.com/nottelabs/notte/stargazers)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/notte?color=blue)](https://pypi.org/project/notte/)
[![PyPI Downloads](https://static.pepy.tech/badge/notte?color=blue)](https://pepy.tech/projects/notte)
[![commits main](https://img.shields.io/github/commit-activity/m/nottelabs/notte?color=blue)](https://github.com/nottelabs/notte/commits/main)
![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/nottelabs/notte?utm_source=oss&utm_medium=github&utm_campaign=nottelabs%2Fnotte&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)

```bash
$ agent.run("go to twitter and post: new era this is @nottecore taking over my acc")
— ft. secure password vault, bypass bot detection, speed x2
```

<p align="center">
  <img src="docs/gifs/v1.gif" alt="Demo" width="100%" href="https://video.twimg.com/ext_tw_video/1892967963344461824/pu/vid/avc1/1282x720/15sCfmmUUcAtBZaR.mp4">
</p>

## Benchmarks

Read the full story here: [https://github.com/nottelabs/open-operator-evals](https://github.com/nottelabs/open-operator-evals)

| Rank | Provider                                                    | Agent Self-Report | LLM Evaluation | Time per Task | Task Reliability |
| ---- | ----------------------------------------------------------- | ----------------- | -------------- | ------------- | ---------------- |
| 🏆   | [Notte](https://github.com/nottelabs/notte)                 | **86.2%**         | **79.0%**      | **47s**       | **96.6%**        |
| 2️⃣   | [Browser-Use](https://github.com/browser-use/browser-use)   | 77.3%             | 60.2%          | 113s          | 83.3%            |
| 3️⃣   | [Convergence](https://github.com/convergence-ai/proxy-lite) | 38.4%             | 31.4%          | 83s           | 50%              |

## Quickstart me

```bash
uv venv --python 3.11
uv pip install notte
uv run patchright install --with-deps chromium
export GEMINI_API_KEY="your-api-key"
```

And spin up your crazy cool and dead simple agent;

```python
from notte import Agent
agi = Agent(reasoning_model="gemini/gemini-2.0-flash")
agi.run(task="doom scroll cat memes on google images")
```

This is by far the closest attempt to AGI we've ever witnessed ;)

## Highlights 🌌

Notte is the full stack framework for web browsing LLM agents. Our main tech highlight is that we introduce a perception layer that turns the internet into an agent-friendly environment, by turning websites into structured maps described in natural language, ready to be digested by an LLM with less effort ✨

```bash
$ page.perceive("https://www.google.com/travel/flights")

# Flight Search
* I1: Enters departure location (departureLocation: str = "San Francisco")
* I3: Selects departure date (departureDate: date)
* I6: Selects trip type (tripType: str = "round-trip", allowed=["round-trip", "one-way", "multi-city"])
* B3: Search flights options with current filters

# Website Navigation
* B5: Opens Google apps menu
* L28: Navigates to Google homepage

# User Preferences
* B26: Open menu to change language settings
...
```

The above gives you the gist of how we push to better parse webpages and reduce the cognitive load of LLM reasoners. The aim is to enable you to build and deploy more accurate web browsing agents, while downgrading to smaller models, which in turn increase inference speed and reduce production costs.

### Speed contest vs. Browser-Use

The perception layer enables smaller models (e.g. the llama suite) to be connected for the agent's reasoning, because all the DOM noise is abstracted and the LLM can focus on a set of actions described in plain language. This allows the agent to be served on ultra-high inference such as Cerebras without losing precision 🏃‍♂️

```bash
$ agent.run("search cheapest flight from paris to nyc on gflight")
— left:browser-use, right:notte-agent (cerebras)
```

<p align="center">
  <img src="docs/gifs/v2.gif" alt="Demo" width="100%" href="https://video.twimg.com/amplify_video/1882896602324418560/vid/avc1/1278x720/Conf_R7LL8htoooT.mp4?tag=16">
</p>

## The full stack framework

Notte's full stack agentic internet framework combines core browser infrastructure (sessions, live replay, cdp) with intelligent browsing agents, bridged and enhanced with our perception layer. Our entire codebase is made to be highly customizable, ready to integrate other devtools from the ecosystem and packaged to be push to prod. We also provide web scripting capabilities and sota scraping endpoints out of the box, because why not.

<table>
  <tr>
    <th><strong>service</strong></th>
    <th><code>agent.run()</code></th>
    <th><code>agent.cloud()</code></th>
    <th><code>page.scrape()</code></th>
    <th><code>page.act()</code></th>
    <th><code>page.perceive()</code></th>
  </tr>
  <tr>
    <td><strong>browser-use</strong></td>
    <td align="center">🌕</td>
    <td align="center">🌕</td>
    <td></td>
    <td></td>
    <td></td>
  </tr>
  <tr>
    <td><strong>stagehand</strong></td>
    <td></td>
    <td></td>
    <td align="center">🌕</td>
    <td align="center">🌕</td>
    <td></td>
  </tr>
  <tr>
    <td><strong>notte</strong></td>
    <td align="center">🌕</td>
    <td align="center">🌕</td>
    <td align="center">🌕</td>
    <td align="center">🌕</td>
    <td align="center">🌕</td>
  </tr>
</table>

PS: The title of services are figurative eg. `agent.cloud()` refers to hosting an agent in cloud for you.

### Unstable and upcoming features

⏭️ We have either already partially shipped or are working on the following features: captcha resolution, residential proxies, web security, vpn-style browsing, authentication and payments with secure safe, improved speed and memory, human-in-the-loop integration, channeled notifications, and cookies management.

## Hosted SDK

We can manage cloud browser sessions and all libraries features for you:

```python
# just append .sdk to import from sdk
from notte_sdk.client import NotteClient
client = NotteClient(api_key="your-api-key")
agent = client.agents.run(task="doom scroll dog memes on google images", reasoning_model="gemini/gemini-2.0-flash")
response = client.agents.wait_for_completion(agent_id=agent.agent_id)
```

To run the above you'll need a notte API key from our [console platform](https://console.notte.cc) 🔑

### API endpoints

Scraping endpoint:

- `/v1/scrape` - Scrape data from a URL

Session management:

- `/v1/sessions/create` - Create a new browser session
- `/v1/sessions/{session_id}/close` - Close a session
- `/v1/sessions/{session_id}/debug` - Get debug information from a session (i.e live CDP url / viewer url)
- `/v1/sessions` - List active sessions

Browser & Page interactions:

- `/v1/env/scrape` - Extract structured data from current page
- `/v1/env/observe` - Get action space (perception) from current page
- `/v1/env/act` - Perform action on current page with text command

Agent launchpad:

- `/v1/agent/run` - Execute agent task
- `/v1/agent/{agent_id}` - Get agent task status
- `/v1/agent/{agent_id}/stop` - Stop running agent
- `/v1/agents/` - List running agent tasks

Read more on our [documentation](https://docs.notte.cc) website. You can cURL all of them 🥰

## The console

Most of our features are also available on our [console Playground](https://console.notte.cc/browse) with a large free-tier!

```bash
$ page.extract("get top 5 latest trendy coins on pf, return ticker, name, mcap")
— webpage scraping, structured schema llm extraction
```

<p align="center">
  <img src="docs/gifs/v3.gif" alt="Demo" width="100%" href="https://video.twimg.com/ext_tw_video/1891808695886991360/pu/vid/avc1/1014x720/uc56Q0q3RGK2h8YM.mp4?tag=12">
</p>

## Contribute

Setup your local working environment;

```bash
uv sync --dev
uv run patchright install --with-deps chromium
uv run pre-commit install
```

Find an issue, fork, open a PR, and merge :)

## License

Notte is released under the [Apache 2.0 license](LICENSE)

## Citation

If you use notte in your research or project, please cite:

```bibtex
@software{notte2025,
  author = {Pinto, Andrea and Giordano, Lucas and {nottelabs-team}},
  title = {Notte: Software suite for internet-native agentic systems},
  url = {https://github.com/nottelabs/notte},
  year = {2025},
  publisher = {GitHub},
  license = {Apache-2.0}
  version = {0.1.3},
}
```

Built with luv from Earth 🌏
