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
