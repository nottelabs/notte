# IBM watsonx.ai with Notte

Capture a page in an owned Notte browser and describe its screenshot through the watsonx.ai REST API. Both examples exchange an IBM Cloud API key for an IAM token, then call image chat. They require a vision-capable model available in your project's region.

Set `NOTTE_API_KEY`, `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, and `WATSONX_MODEL_ID` in your shell. `WATSONX_URL` defaults to `https://us-south.ml.cloud.ibm.com`; change it to your project's [regional endpoint](https://cloud.ibm.com/docs/apis/watsonx-ai).

Python 3.11+, from this directory:

```sh
uv sync --locked
uv run --locked python python/demo.py
```

Node.js 24+, from `typescript`:

```sh
npm ci
npm start
```

The result contains the model's description and the closed browser's session ID. Each run closes its browser on capture, authentication, or model errors. Failures report the stage and HTTP status without response bodies or credentials. Only use pages whose screenshots you intend to send to IBM.

## Verification

`uv run --locked python -m unittest discover -s python` and `npm test` check IAM authentication, image chat payloads, invalid tokens, HTTP rejection, and empty model results without contacting IBM.

For real Notte capture, rejection, privacy, and authoritative session-closure checks, set `NOTTE_WATSONX_PYTHON` to this directory's `.venv/bin/python`, then run `npm run test:live` from `typescript`. These tests inject IBM HTTP responses while transporting actual browser screenshots. CI requires the Notte key and runs against published and source SDKs.

A live IBM account and model inference have not been tested. The injected responses validate the documented HTTP contract, not model availability, project permissions, or screenshot interpretation.
