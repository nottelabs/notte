// Narrative guidance complements compiler-derived API signatures. Runnable examples
// belong in docs/src/testers, not in these templates.
export const gettingStartedGuides = [
  {
    slug: 'authentication',
    title: 'Authentication',
    content: `The Node SDK authenticates requests using your API key.

## Get your API key

Get an API key from the [Notte Console](https://console.notte.cc). Keep it on your server; do not expose it in browser bundles or commit it to source control.

## Environment variable

Set \`NOTTE_API_KEY\` in your server environment. [NotteClient](/typescript-sdk-reference/manual/client) reads it automatically when no API key is provided in its configuration.

## Client configuration

Pass \`apiKey\` in the client configuration to override the environment variable. See [NotteClientConfig](/typescript-sdk-reference/types/notteclientconfig) for the generated options.

The API URL defaults to \`https://api.notte.cc\`. Override it with \`NOTTE_API_URL\` or the client’s \`baseUrl\` option. An explicit non-empty option takes precedence over the environment variable.

## Authentication errors

A missing key throws during client construction, except when using a relative proxy URL. Invalid keys are rejected by the API when a request is made. See [Error Handling](/typescript-sdk-reference/errors).`,
  },
  {
    slug: 'errors',
    title: 'Error Handling',
    content: `Handle asynchronous SDK operations with \`await\` inside \`try/catch\`.

## Configuration errors

[NotteClient](/typescript-sdk-reference/manual/client) throws \`AuthenticationError\` for a missing API key and \`InvalidRequestError\` for an unsupported API URL. HTTPS is required for remote servers; HTTP is allowed on loopback for local development.

## API and execution errors

HTTP failures throw [NotteAPIError](/typescript-sdk-reference/manual/notteapierror), with \`statusCode\`, \`path\`, the parsed error body, and the response when available. Request deadlines throw [NotteTimeoutError](/typescript-sdk-reference/manual/nottetimeouterror). Failed actions throw \`ActionExecutionError\`; failed cloud function runs throw \`FailedToRunCloudFunctionError\` unless \`raiseOnFailure: false\` is set.

Treat caught values as \`unknown\`: check \`error instanceof Error\` before reading \`error.message\`. Do not depend on parsing error messages to identify HTTP status codes.

## Session cleanup

Use [Session.use](/typescript-sdk-reference/session/use) for managed sessions. It starts the session before your callback and stops it when the callback finishes, including when it throws. Catch errors around the awaited \`use()\` call so failures reach your error handler.

## Retrying failures

Do not retry every exception: configuration errors require a fix, and repeating a state-changing operation may duplicate work. See [Rate Limits](/typescript-sdk-reference/rate-limits) for retry considerations.`,
  },
  {
    slug: 'rate-limits',
    title: 'Rate Limits',
    content: `The API returns HTTP \`429\` when a rate limit is exceeded. See the [API rate-limit reference](/api-reference/rate-limits) for response headers.

## Handling rate limits

Check \`error instanceof NotteAPIError\` and \`error.statusCode === 429\` to identify rate limiting. Response headers are available through \`error.response?.headers\`; Node uses \`statusCode\`, not Python’s \`status_code\`.

When your HTTP integration exposes a verified \`429\` response, honor \`Retry-After\` if provided; otherwise use bounded exponential backoff with jitter. Set a retry limit and retry only operations that are safe to repeat. Automatic rate-limit retries are not provided by the high-level client.

## Reduce request volume

Limit concurrent requests, avoid repeatedly polling unchanged state, and reuse results when your application can safely do so.

## Increasing limits

[Contact us](https://cal.com/team/notte/demo) to discuss higher limits.`,
  },
];
