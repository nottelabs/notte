# How to change the local notte config

If you want to change any parameter of the [notte config](../packages/notte-core/src/notte_core/config.toml), you can do it by creating a `notte_config.toml` file and exporting the `NOTTE_CONFIG_PATH` environment variable to the path of your `notte_config.toml` file.

```bash
export NOTTE_CONFIG_PATH="path/to/your/notte_config.toml"
```

For instance, if you want to run local browsers in headless mode, you can create a blank `notte_config.toml` file and add the following:

```toml
headless = true
```

Note that it is very important to export the `NOTTE_CONFIG_PATH` environment variable before importing any notte module.

```python
import os
os.environ["NOTTE_CONFIG_PATH"] = "path/to/your/notte_config.toml"
import notte
```

Otherwise, the default config will be used and your changes will not be applied.

## LLM settings

The config file only covers browser, DOM parsing and timeout settings. Local LLM features (structured `scrape(instructions=..., response_format=...)` on a local `notte.Session`) are an optional extra installed with `pip install 'notte[llm]'`, and they are configured through environment variables instead:

Set `OPENROUTER_API_KEY` to use OpenRouter with `google/gemini-3.5-flash` by default.
For another OpenAI-compatible endpoint, set all three of `NOTTE_LLM_BASE_URL`,
`NOTTE_LLM_API_KEY`, and `NOTTE_LLM_MODEL` (the endpoint's own model ID):

- OpenAI: `NOTTE_LLM_BASE_URL=https://api.openai.com/v1`, `NOTTE_LLM_MODEL=gpt-4o`.
- Gemini: `NOTTE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `NOTTE_LLM_MODEL=gemini-3.5-flash`.
- Ollama/custom: `NOTTE_LLM_BASE_URL=http://localhost:11434/v1`, your local model ID, and `NOTTE_LLM_API_KEY=ollama` for an unauthenticated local server. Ollama has not been live-tested.

`NOTTE_LLM_API_KEY` overrides `OPENROUTER_API_KEY`. The latter is used only at the default
OpenRouter URL, so it is never sent to a custom endpoint. The per-call `model=` argument
selects a model at the configured endpoint without translating its ID.

| Variable | Default |
| --- | --- |
| `NOTTE_LLM_BASE_URL` | `https://openrouter.ai/api/v1` |
| `NOTTE_LLM_API_KEY` | `OPENROUTER_API_KEY` at the default URL; required elsewhere |
| `NOTTE_LLM_MODEL` | `google/gemini-3.5-flash` at the default URL; required elsewhere |
| `NOTTE_LLM_TEMPERATURE` | `0.0` |
| `NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT` | `2` |
| `NOTTE_LLM_CONTEXT_TOKENS` | `128000` (document clipping estimates four characters per token) |

## JavaScript result size

`evaluate_js_max_result_bytes` defaults to 16777216 (16 MiB). It limits the UTF-8
text returned by `evaluate_js`, including escaped JSON and indentation. The value
is first measured inside the page, and a result whose data alone exceeds the
limit is rejected before the browser transfers it. The exact budget, including
indentation, is applied during conversion.
Either check returns a failed action advising you to return fewer fields or
retrieve the result in smaller batches.
Values within the limit keep their existing text format. JSON nesting is limited
to 128 levels.

`evaluate_js_max_result_values` defaults to 50000. It limits how many values a
result may contain, counting every string, number, boolean, null, array and
object, including repeated references. Transferring a result costs memory per
value regardless of its formatted size, so this is checked in the page before
anything is transferred. A larger result fails with the same advice.

```toml
evaluate_js_max_result_bytes = 16777216
evaluate_js_max_result_values = 50000
```

This is an output budget, not a hard process-memory limit. It bounds conversion
buffering, but excludes the browser result already decoded into Python and memory
used by other concurrent requests. Raising it increases the possible memory peak.
