# Stripe Link with Notte

Retrieve an approved Link test credential with the native Python or TypeScript SDK and fill a Notte browser form. The example checks the filled values and closes the browser. It never submits a payment.

Set:

- `NOTTE_API_KEY` from [Notte](https://console.notte.cc/apikeys).
- `LINK_ACCESS_TOKEN` from your application's Link authorization flow. The [Link SDKs](https://github.com/stripe/link-cli#sdks) accept application-managed tokens; a Stripe secret key is not needed.
- `LINK_SPEND_REQUEST_ID` for an approved **test-mode card** spend request. Use Link CLI's `spend-request create --test` and approve it in your Link wallet. See the [test-mode lifecycle](https://github.com/stripe/link-cli#spend-request-lifecycle). The example accepts only Link's published test card and rejects other cards.

From this directory:

```sh
# Python 3.11+, uv
uv sync --locked
uv run python python/demo.py

# TypeScript, Node.js 24+
cd typescript
npm ci
npm start
```

`fill_approved_test_card(page, wallet, request_id)` and `fillApprovedTestCard(page, wallet, requestId)` read the credential directly into the test form. Card data stays out of output and model prompts. This is a credential-fill example; adapt an actual purchase flow to its merchant, require the user's approval, submit once, and verify the merchant's order confirmation before reporting a purchase.

Verified on real Notte browsers with published and source Notte SDKs: native Link response parsing, test-form fill, genuine Link HTTP 401 errors, private error-body suppression, and independently queried browser closure. Successful approval and credential issuance by a Link wallet have not been live-tested.

Offline tests use the native SDK with controlled HTTP responses. Run `.venv/bin/python -m unittest discover -s python` and, from `typescript`, `npm test`. With a Notte key, run `NOTTE_LINK_PYTHON=../.venv/bin/python npm run test:live`; approved-wallet cases run only when the two Link variables are configured. CI requires browser/protocol and rejection checks without a wallet credential.
