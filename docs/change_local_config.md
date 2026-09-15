# How to change the local notte config

If you want to change any parameter of the [notte config](../packages/notte-core/src/notte_core/config.toml), you can do it by creating a `notte_config.toml` file and exporting the `NOTTE_CONFIG_PATH` environment variable to the path of your `notte_config.toml` file.

```bash
export NOTTE_CONFIG_PATH="path/to/your/notte_config.toml"
```

For instance, if you want to change the temperature of the LLM, you can create a blank `notte_config.toml` file and add the following:

```toml
temperature = 0.5
```

Note that it is very important to export the `NOTTE_CONFIG_PATH` environment variable before importing any notte module.

```python
import os
os.environ["NOTTE_CONFIG_PATH"] = "path/to/your/notte_config.toml"
import notte
```

Otherwise, the default config will be used and your changes will not be applied.

## JavaScript result size

`evaluate_js_max_result_bytes` defaults to 16777216 (16 MiB). It limits the UTF-8
text returned by `evaluate_js`, including escaped JSON and indentation. Conversion
stops at the limit and returns a failed action advising you to return fewer fields
or retrieve the result in smaller batches. Values within the limit keep their
existing text format. JSON nesting is limited to 128 levels.

```toml
evaluate_js_max_result_bytes = 16777216
```

This is an output budget, not a hard process-memory limit. It bounds conversion
buffering, but excludes the browser result already decoded into Python and memory
used by other concurrent requests. Raising it increases the possible memory peak.
