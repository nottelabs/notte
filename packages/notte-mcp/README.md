# Notte MCP Server

<div align="center">
  <h1>Notte MCP Server</h1>
  <p><em>MCP server for all Notte tools in the agentic ecosystem.</em></p>
  <p><strong>Manage your sessions. Run agents. Take control: observe, scrape, act, authenticate.</strong></p>
  <hr/>
</div>
[The Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) provides a standardized protocol for connecting LLM applications with external tools and data sources. It enables seamless integration between language models and the context they need, whether you're developing an AI-powered IDE, building a chat interface, or designing custom AI workflows.

## Available Tools

### Session Management

| Tool | Description |
|------|-------------|
| `notte_start_session` | Start a new cloud browser session |
| `notte_list_sessions` | List all active browser sessions |
| `notte_stop_session` | Stop the current session |

### Page Interaction & Scraping

| Tool | Description |
|------|-------------|
| `notte_observe` | Observe elements and available actions on the current page |
| `notte_screenshot` | Take a screenshot of the current page |
| `notte_scrape` | Extract structured data from the current page |
| `notte_step` | Execute an action on the current page |

### Agent Operations

| Tool | Description |
|------|-------------|
| `operator` | Run a Notte agent to complete a task on any website |

## Getting Started

1. Install the required dependencies:
```bash
pip install notte-mcp
```

2. Set up your environment variables:
```bash
export NOTTE_API_KEY="your-api-key"
```

3. Start the MCP server:
```bash
python -m notte_mcp.server
```

> note: you can also start the server locally using `uv run mcp dev packages/notte-mcp/src/notte_mcp/server.py  --with-editable .`

To use the MCP in cursor or claude computer use, you can use the following json:

```json
{
    "mcpServers": {
        "notte-mcp": {
            "url": "http://localhost:8000/sse",
            "env": {
                "NOTTE_API_KEY": "<your-notte-api-key>"
            }
        }
    }
}
```
