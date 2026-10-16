# Evervault Browser Tokens

**Pending Notte runtime rollout.** These examples require a Notte environment that verifies the `evervault` browser trust profile. They refuse to connect or navigate when the start response lacks the expected profile and certificate fingerprint.

Create a short-lived password token with [Evervault Browser Tokens](https://docs.evervault.com/browser-tokens), then fill that token into an HTTPS form you own. The browser runs through Evervault's HTTPS proxy. The example fills `input[name="password"]` and closes the session; it does not submit the form or make a payment.

Set these environment variables without committing their values:

| Variable | Value |
| --- | --- |
| `NOTTE_API_KEY` | Your [Notte API key](https://console.notte.cc) |
| `EVERVAULT_APP_ID`, `EVERVAULT_API_KEY` | Credentials for an Evervault app with Browser Tokens access |
| `EVERVAULT_ENCRYPTED_PASSWORD` | An existing Evervault-encrypted value beginning with `ev:` |
| `EVERVAULT_FORM_URL` | Your owned HTTPS form or approved sandbox login URL |
| `NOTTE_API_URL` | Optional Notte API endpoint; defaults to `https://api.notte.cc` |

Browser Tokens are a vendor preview. Use the [Evervault documentation](https://docs.evervault.com/browser-tokens) for access and encrypted-value collection.

## Run

Python 3.11+:

```sh
cd examples/evervault/python
uv sync --locked
uv run python main.py
```

Node.js 24+:

```sh
cd examples/evervault/typescript
npm ci
npm start
```

The encrypted input and Evervault app credentials go only to Evervault. Notte receives the token's proxy configuration and a three-minute browser limit. Only the returned password token is filled into the form. The decrypt permission covers the form's exact hostname; navigation to another origin fails before filling.

Both languages require Notte's verified `evervault` profile and pinned CA fingerprint before CDP lookup. They keep certificate verification enabled, stop only their owned session, and GET-confirm persisted closure on success, failure, or cancellation. The token TTL is five minutes. Keep the proxy credentials private and discard them after use.

## Verification

Run `uv run pytest` in `python` and `npm run typecheck && npm test` in `typescript`. Protocol fixtures check request boundaries, trust refusal, redaction, cancellation, and cleanup. These fixtures do not demonstrate Evervault's hosted proxy replacement.

With a local Notte key, set `NOTTE_EVERVAULT_LIVE=1`, then run `uv run pytest -x` in `python` or `npm run test:live` in `typescript`. These add an ordinary Notte browser/form control and an unknown-profile refusal check, stopping after a failed control. They send no Evervault credentials or proxy JWE. Hosted Evervault tokenization and plaintext replacement remain unverified; a deployed Notte trust-profile browser proof is also pending. Do not treat these tests as a complete hosted integration test.

After the trust-profile runtime is available, `NOTTE_EVERVAULT_PROFILE_LIVE=1` explicitly enables a Notte trust-profile acceptance test with an ordinary HTTPS page and dummy form. It needs only a Notte key, requires both trust markers, and never treats an unsupported profile as success. This verifies runtime setup, not Evervault interception.
