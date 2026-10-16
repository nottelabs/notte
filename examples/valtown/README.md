# Val Town with Notte

Run a browser task from a Val Town HTTP trigger. The example uses Deno's built-in `fetch` to open a Notte session, read Example Domain's title, and close the browser before responding. It needs no local browser, filesystem access, or model key.

Create a val at [Val Town](https://www.val.town/new), copy `main.ts` into it, and add an HTTP trigger. In the val's Environment Variables sidebar, set:

- `NOTTE_API_KEY`: a [Notte API key](https://console.notte.cc/apikeys).
- `NOTTE_VALTOWN_TOKEN`: a private invocation token you choose.

Send a POST request to the trigger URL with `Authorization: Bearer <NOTTE_VALTOWN_TOKEN>`. The response contains `title` and the closed browser's `session_id`. Requests without the invocation token cannot create browsers. The sample uses a fixed target; edit `readPage` to adapt the task.

Local verification with Deno 2.9.6:

```sh
cd examples/valtown
deno task check
deno task test
```

The default tests use fake API responses and deny network access. To verify real navigation, failure cleanup, and persisted browser closure, choose your endpoint explicitly:

```sh
export NOTTE_API_URL=https://api.notte.cc
export NOTTE_VALTOWN_LIVE=1
deno task test:live
```

See Val Town's [HTTP triggers](https://docs.val.town/vals/http) and [environment variables](https://docs.val.town/reference/environment-variables) guides. Its [API token settings](https://www.val.town/settings/api) are needed only when managing your val through the API; running this example does not require a Val Town API token.
