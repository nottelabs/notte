# Docker Sandboxes with Notte

Connect a local Docker Sandboxes coding agent to Notte Browser MCP through Sandboxes' native host-managed gateway. The setup uses the current standalone `sbx` CLI.

Install [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/install/) 0.48+, run `sbx login`, and configure your coding agent's usual authentication. Get a [Notte API key](https://console.notte.cc/apikeys).

Run `sh /path/to/notte/examples/docker-sandboxes/setup.sh claude notte-browser` from your intended workspace. The script registers the hosted MCP endpoint, prompts for the Notte key through `sbx secret set`, then starts Claude with `--static-mcp notte`. Substitute a supported agent such as `codex` if preferred. The literal header placeholder resolves from the host credential store; the key is not put in shell arguments or the sandbox environment.

Ask the agent to start a Notte browser, visit `https://example.com`, observe its title, and stop that browser even if a step fails. Stop the local sandbox afterward with `sbx stop notte-browser`. A sandbox and its remote browser have separate lifecycles.

For independent protocol verification, use Node.js 24+, run `npm ci`, set `NOTTE_API_KEY`, and run `node src/main.ts`. Set `NOTTE_SANDBOXES_LIVE=1` and an explicit `NOTTE_API_URL` for `npm run test:live`. These tests exercise real MCP browser actions and authoritative closed-session checks. `npm test` checks secret handling and setup failure behavior.

Native CLI command contracts are validated against Docker's pinned release in CI. A complete coding-agent run inside a native sandbox has not been tested because the local runtime is unavailable on this host. See Docker's [MCP gateway guide](https://docs.docker.com/ai/sandboxes/mcp-gateway/) for gateway behavior.
