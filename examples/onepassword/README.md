# 1Password with Notte

Read login fields through the official 1Password SDK and fill a Notte browser form. The examples submit an in-memory test form, verify the filled values, and return only the session ID and submission result. They close their browser on success or error.

Create a [service account](https://start.1password.com/developer-tools/infrastructure-secrets/serviceaccount/) with read access to a test vault containing a dummy Login item. Set `OP_SERVICE_ACCOUNT_TOKEN`, `OP_USERNAME_REF`, and `OP_PASSWORD_REF`. References look like `op://vault/item/username` and `op://vault/item/password`; [1Password documents the syntax](https://www.1password.dev/sdks/load-secrets). Also set `NOTTE_API_KEY` from [Notte](https://console.notte.cc/apikeys).

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

Reuse `fill_login(page, username_ref, password_ref)` or `fillLogin(page, usernameRef, passwordRef)` on your login page. Adapt the Username, Password, and Sign in locators to that page. The helper reads only the two requested fields and does not print their values.

From `typescript`, run `NOTTE_ONEPASSWORD_PYTHON=../.venv/bin/python npm run test:live` after installing both projects. Native reference validation runs without keys. Browser cleanup after a rejected token requires `NOTTE_API_KEY`; successful vault reads require all four environment variables. Tests independently query each owned browser's final status.
