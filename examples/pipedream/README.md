# Connected apps with Pipedream

Use separate native MCP clients for Notte browser tools and Pipedream connected
apps. The demo reads `example.com`, discovers the selected app's tools, and
closes its browser. By default it only discovers tools. An optional, explicitly
approved tool call uses the same native client. No model selects actions.

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
count, and whether an optional tool call completed. `PIPEDREAM_APP` defaults to `github`; requests use Pipedream's development
environment.

The code exchanges client credentials at Pipedream's documented OAuth endpoint,
then sends its access token and project/user/app headers to the hosted v3 MCP
endpoint. Keep this code server-side and derive the external user from your
authenticated application. Notte and Pipedream credentials are independent.

Discovery does not classify every advertised tool as read-only. To opt in to one
call, first select its actual advertised name and schema, complete the provider
connection, and obtain the required approval. Create a private JSON file outside
the checkout with exactly `name` (the offered tool name) and `arguments` (an
object matching its schema). Set `PIPEDREAM_ACTION_FILE` to its path. Do not put
private arguments in shell command arguments or commit the file.

The demo rejects names absent from discovery and MCP error results. It discards
provider output and prints only `tool_call_completed`; this confirms a successful
MCP response, not a verified vendor side effect. Pipedream can return a Connect
Link when a tool needs an account connection; discovery alone does not launch
OAuth. This example adds neither built-in Notte OAuth UI nor automatic
connected-app tools to Notte Agent API runs.

Maintainers can run `uv run --locked python -m unittest test_live -v` and
`npm test` with only `NOTTE_API_KEY`. `NOTTE_API_URL` selects a Notte environment.
These tests use real Notte browsers and native MCP clients with a local Pipedream
protocol fixture. Discovery, synthetic action success/error, unoffered-tool rejection, OAuth/MCP
HTTP 401, failed navigation, pagination/cursor refusal, CLI interruption and
Python claim-time cancellation all receive independent session-closure checks. No Pipedream credentials are used.

Hosted Pipedream OAuth and vendor action execution have not been tested.
