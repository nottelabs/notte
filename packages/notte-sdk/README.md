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
client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# Run an AI agent
agent = client.agents.run(
    task="What is the capital of France?",
    url="https://www.google.com",
)

# Monitor agent status
status = client.agents.status(agent.agent_id)
```

## Core Components

### Session Management

The SDK provides comprehensive session management capabilities:

```python
# Start a new session
with client.Session(timeout_minutes=5) as session:
    # Get session status
    status = client.sessions.status(session.session_id)

    # View live session
    session.viewer()
```

### Agent Operations

Deploy and manage AI agents for automated tasks:

```python
# Run an agent with specific tasks
agent = client.agents.run(
    task="Summarize the content of the page",
    url="https://www.google.com"
)

# List active agents
agents = client.agents.list()

# Stop an agent
client.agents.stop(agent_id=agent.agent_id)
```

### Web Automation

Execute web automation tasks with built-in tools:

```python
with client.Session() as session:
    # Observe a web page
    obs = session.page.observe(url="https://www.google.com")

    # Execute actions
    action = obs.space.sample(role='link')
    data = session.page.step(action_id=action.id)

    # Scrape content
    data = session.page.scrape(url="https://www.google.com")
```

### CDP Integration

Integrate with Chrome DevTools Protocol for advanced browser control:

```python
from patchright.sync_api import sync_playwright

with client.Session(proxies=False) as session:
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
