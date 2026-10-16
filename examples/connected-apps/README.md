# Connected apps with Quaso

Discover app connections and typed actions using the Notte API key for your
Quaso workspace. This example uses Python 3.11+ or Node.js 24.8+ with no extra
dependencies.

Prerequisite: the connected-app discovery API must be available on Quaso.
Connect an app in [Quaso Settings](https://www.quaso.ai/settings#integrations),
then set `NOTTE_API_KEY` for that same workspace. In this directory run
`python connected_apps.py` or `npm start`. Optionally set `CONNECTED_APP` to a
catalog slug such as `github` or `gmail`. The output contains app, connected
account and action counts. It performs only metadata reads.

`discover` returns catalog entries, matching accounts and up to ten action
summaries. Select a healthy account and an action belonging to the same app.
`run_action` / `runAction` accepts that account ID, the discovered action key
and the action's configured properties. Provider authentication is attached
server-side; do not supply auth properties. Action schemas and required
properties depend on the provider. Review any operation with side effects
before invoking it; the demo does not execute actions.

OAuth connection and disconnection happen in Quaso's UI. This is not automatic
connected-app tool injection into Notte Agent API runs or a programmable OAuth
lifecycle. The live catalog includes OAuth and API-key providers.

Run `python -m unittest -v` and `npm test` for local HTTP protocol tests. These
cover metadata discovery, a read-only action fixture, HTTP errors and rejected
redirects. Live OAuth and vendor action execution have not been tested.
