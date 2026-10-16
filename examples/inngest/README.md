# Notte with Inngest AgentKit

Give an AgentKit agent a browser tool. Each tool call starts a Notte session, reads the page title with Playwright, and closes the session on success or failure.

Requires Node.js 24+, a [Notte API key](https://console.notte.cc), and an [Anthropic API key](https://platform.claude.com/settings/keys).

```bash
npm ci
export NOTTE_API_KEY=your-notte-api-key
export ANTHROPIC_API_KEY=your-anthropic-api-key
npm start
```

The agent calls `page_title` for `https://example.com`. Its tool result includes `title: "Example Domain"` and the stopped session's `session_id`. No local browser installation is needed.

This runs AgentKit directly. To add durable execution, serve the agent using [AgentKit's Inngest setup](https://agentkit.inngest.com/getting-started/quick-start).

For live tests, choose `NOTTE_API_URL` explicitly and set `NOTTE_INNGEST_LIVE=1`. Set `NOTTE_INNGEST_MODEL_LIVE=1` to include the real model/tool call. Run `npm run test:live`.
