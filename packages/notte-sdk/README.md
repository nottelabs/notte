# Notte SDK

The Notte SDK is a powerful Python library that provides a seamless interface for interacting with web automation and AI-powered agents. It enables developers to create, manage, and monitor web automation sessions and AI agents with ease.

## Key Features

- **Session Management**: Create, monitor, and control web automation sessions
- **Agent Orchestration**: Deploy and manage AI agents for automated web tasks
- **CDP Integration**: Direct Chrome DevTools Protocol integration for advanced browser control
- **Web Automation**: Built-in tools for web page observation, scraping, and action execution
- **Real-time Monitoring**: Live session viewing and debugging capabilities

## Installation

```bash
pip install notte-sdk
```

## Quick Start

```python
import os
from notte_sdk import NotteClient

# Initialize the client
notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# Run an AI agent
with notte.Session(headless=False) as session:
    agent = notte.Agent(session=session)
    agent.run(
        task="What is the capital of France?",
        url="https://www.google.com",
    )
```

## Core Components

### Session Management

The SDK provides comprehensive session management capabilities:

```python
from notte_sdk import NotteClient
notte = NotteClient()

# Start a new session
with notte.Session(timeout_minutes=5) as session:
    # Get session status
    status = session.status()
    # View live session
    session.viewer()
```

### Agent Operations

Deploy and manage AI agents for automated tasks:

```python
from notte_sdk import NotteClient
notte = NotteClient()
# Run an agent with specific tasks

with notte.Session(headless=False) as session:
    agent = notte.Agent(session=session)
    # Start an agent with non-blocking call
    agent.start(
        task="Summarize the content of the page",
        url="https://www.google.com"
    )

# Monitor agent status
status = agent.status()
# List active agents
agents = notte.agents.list()

# Stop an agent
agent.stop()


```

### Web Automation

Execute web automation tasks with built-in tools:

```python
from notte_sdk import NotteClient
notte = NotteClient()

with notte.Session(headless=False) as session:
    # Observe a web page
    _ = session.execute(type="goto", url="https://www.google.com")
    obs = session.observe()
    # Execute actions
    action = obs.space.sample(type='click')
    data = session.step(action=action)
    # Scrape content
    data = session.scrape(url="https://www.google.com")
```

### CDP Integration

Integrate with Chrome DevTools Protocol for advanced browser control:

```python
from patchright.sync_api import sync_playwright
from notte_sdk import NotteClient
notte = NotteClient()

with notte.Session(proxies=False) as session:
    cdp_url = session.cdp_url()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        page = browser.contexts[0].pages[0]
        page.goto("https://www.google.com")
```

## Advanced Features

- Real-time session monitoring and debugging
- Automated web scraping and content analysis
- AI-powered task automation
- Flexible session configuration
- Comprehensive error handling and logging

## Support

For support, please contact us at [hello@notte.cc](mailto:hello@notte.cc)
