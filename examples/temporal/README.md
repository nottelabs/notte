# Notte with Temporal

Run a Notte browser task as a Temporal Activity. Requires Node.js 24+, a [Notte API key](https://console.notte.cc), and the [Temporal CLI](https://docs.temporal.io/cli).

Start a local Temporal server in one terminal:

```bash
temporal server start-dev
```

In this directory, start the worker in a second terminal:

```bash
npm ci
npm run build
export NOTTE_API_KEY=your-notte-api-key
npm run worker
```

In a third terminal, run `npm start` from this directory. The result includes `title: "Example Domain"` and the stopped session's `session_id`.

The Workflow schedules an Activity; browser calls stay inside that Activity, outside deterministic Workflow code. Every retry creates a new session. The Activity closes its browser on success or failure. A three-minute session limit also bounds browser lifetime if the worker process dies before cleanup.

The Workflow allows up to three Activity attempts. Keep the example read-only; operations with external side effects need idempotency before automatic retries. No local Chromium installation is needed.

`TEMPORAL_ADDRESS` and `TEMPORAL_NAMESPACE` default to `localhost:7233` and `default`. For cloud authentication, follow [Temporal's connection guide](https://docs.temporal.io/develop/typescript/temporal-client).

For live tests, set `NOTTE_API_KEY`, choose `NOTTE_API_URL` explicitly, and set `NOTTE_TEMPORAL_LIVE=1`. Run `npm run test:live`; it starts and stops its own local Temporal server and verifies a successful Workflow, three failed Activity attempts, and cleanup of all four browsers.
