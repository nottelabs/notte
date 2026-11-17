/**
 * Opts in to the `rejected` function run status (a run whose function raised an
 * `ExpectedFunctionError`). Without it the API reports rejected runs as `failed`,
 * so clients that predate the status still treat them as failures. `NotteClient`
 * sends it on every functions request, like `RESOURCE_HEADERS` of the Python
 * functions client, and the proxy forwards it.
 *
 * Kept free of imports so the proxy entry point can share it without bundling the client.
 */
export const ACCEPT_RUN_STATUSES_HEADER = 'x-notte-accept-run-statuses';
