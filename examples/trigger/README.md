# Notte with Trigger.dev

Run a browser task on Trigger.dev using a Notte cloud session. Requires Node.js 24+, a Notte API key, and a Trigger.dev project.

```bash
npm ci
export NOTTE_API_KEY=your-notte-api-key
export TRIGGER_PROJECT_REF=your-project-reference
export TRIGGER_SECRET_KEY=your-development-api-key
npm run dev
```

Log in when the CLI prompts, or set `TRIGGER_ACCESS_TOKEN` using a [personal access token](https://cloud.trigger.dev/account/tokens).

In your project's development dashboard, test `notte-read-page` with:

```json
{"url":"https://example.com"}
```

The output contains `title` and `session_id`. Each attempt creates its own browser and closes it before returning or propagating an error. The task allows up to three attempts, so keep this example read-only. A three-minute session limit also bounds browser lifetime if the worker is terminated before cleanup runs.

For deployment, follow [Trigger.dev's deployment guide](https://trigger.dev/docs/deploy). Configure `NOTTE_API_KEY` in the target Trigger.dev environment. No local Chromium installation is needed.
