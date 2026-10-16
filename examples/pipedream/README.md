# Connected apps with Pipedream

Use separate native MCP clients for Notte browser tools and Pipedream connected
apps. The demo reads `example.com`, discovers the selected app's tools, and
closes its browser. It never invokes Pipedream actions or sends messages.

Use Python 3.11+ or Node.js 24.8+, a [Notte API key](https://console.notte.cc/apikeys),
and your own Pipedream [project](https://pipedream.com/projects) and
[OAuth client](https://pipedream.com/settings/api). Follow Pipedream's
[developer setup](https://pipedream.com/docs/connect/mcp/developers) for account
connections. No provider SDK is needed.

In this directory, run `uv sync --locked` for Python or `npm ci` for TypeScript.
Set `NOTTE_API_KEY`, `PIPEDREAM_CLIENT_ID`, `PIPEDREAM_CLIENT_SECRET`,
`PIPEDREAM_PROJECT_ID`, and `PIPEDREAM_EXTERNAL_USER_ID`. The last value is your
application's stable end-user identifier. Run `uv run --locked python demo.py`
or `npm start`. Output contains the stopped browser's ID and discovered tool
count. `PIPEDREAM_APP` defaults to `github`; requests use Pipedream's development
environment.

The code exchanges client credentials at Pipedream's documented OAuth endpoint,
then sends its access token and project/user/app headers to the hosted v3 MCP
endpoint. Keep this code server-side and derive the external user from your
authenticated application. Notte and Pipedream credentials are independent.

Discovery does not classify every advertised tool as read-only. Before invoking
an action elsewhere, select its real advertised name and schema, obtain any
required human approval, and complete the provider's connection flow. Pipedream
can return a Connect Link when a tool needs an account connection; discovery
alone does not launch OAuth. This example adds neither built-in Notte OAuth UI
nor automatic connected-app tools to Notte Agent API runs.

Maintainers can run `uv run --locked python -m unittest test_live -v` and
`npm test` with only `NOTTE_API_KEY`. `NOTTE_API_URL` selects a Notte environment.
These tests use real Notte browsers and native MCP clients with a local Pipedream
protocol fixture. Success, OAuth/MCP HTTP 401, failed navigation and cancellation
all receive independent session-closure checks. No Pipedream credentials are used.

Hosted Pipedream OAuth and vendor action execution have not been tested.
