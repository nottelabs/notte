import os
from pathlib import Path

import notte_core

CONFIG_PATH = Path(__file__).parent / "test_notte_config.toml"
notte_core.set_error_mode("developer")

os.environ["NOTTE_CONFIG_PATH"] = str(CONFIG_PATH)


# if we run in Github Actions, we need to disable GPU
if os.getenv("GITHUB_ACTIONS") is not None:
    os.environ["DISABLE_GPU"] = "true"
