# Prime Intellect with Notte

A [Verifiers 0.4](https://docs.primeintellect.ai/verifiers/v1/overview) taskset that gives each rollout its own Notte browser. Its MCP `read_page` tool reads a page title; the reward checks the observed title and URL. The environment closes the browser in `finally`, including on provider failures. Each trace keeps its own browser handle, even when Verifiers reuses the task for concurrent rollouts.

```sh
cd examples/prime-intellect
uv sync --locked
export NOTTE_API_KEY=your-notte-api-key
export PRIME_API_KEY=your-prime-inference-key
uv run --locked vf-eval notte_prime --env.agent.runtime.type subprocess \
  --env.agent.max_turns 3 --no-push -n 1 -c 1
```

Get a [Notte key](https://console.notte.cc/apikeys) and configure [Prime Inference](https://docs.primeintellect.ai/inference/overview). Verifiers also supports a custom OpenAI-compatible endpoint through `--client.base_url` and `--client.api_key_var`. Model inference can incur provider charges. The command uses a local harness process and does not upload its results; browsers run on Notte.

The tool's schema contains only the navigation URL. The session endpoint travels through Verifiers' authenticated private state channel, which is excluded from serialized traces. Model arguments cannot choose another session. Keep the tool server on a trusted runtime.

## Verify

```sh
DISABLE_TELEMETRY=true uv run --locked python -m unittest -v test_notte_prime.py
```

Default tests exercise the native MCP protocol, state channel, scoring, and error cleanup with fake browsers. To use real Notte browsers, also set `NOTTE_API_KEY`, `NOTTE_PRIME_LIVE=1`, and an explicit `NOTTE_API_URL`, then repeat the command. Live tests also run the full framework against an injected provider 401, and independently check every owned session for persisted closure.

Real Notte browser and framework tool tests pass. Paid model rollouts and hosted Prime training have not been verified. Use the [Verifiers evaluation guide](https://docs.primeintellect.ai/verifiers/v1/evaluation) before adapting this taskset to training.
