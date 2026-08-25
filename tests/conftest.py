import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import notte_core

CONFIG_PATH = Path(__file__).parent / "test_notte_config.toml"
notte_core.set_error_mode("developer")

os.environ["NOTTE_CONFIG_PATH"] = str(CONFIG_PATH)


# if we run in Github Actions, we need to disable GPU
if os.getenv("GITHUB_ACTIONS") is not None:
    os.environ["DISABLE_GPU"] = "true"


def _load_ci_vault_scope() -> Any | None:
    if not os.environ.get("NOTTE_CI_VAULT_PREFIX"):
        return None
    path = Path(__file__).resolve().parents[1] / "scripts" / "ci_vault_scope.py"
    spec = importlib.util.spec_from_file_location("ci_vault_scope", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_vault_scope"] = module
    spec.loader.exec_module(module)
    return module


_CI_VAULT_SCOPE = _load_ci_vault_scope()
if _CI_VAULT_SCOPE is not None:
    _CI_VAULT_SCOPE.install()


# Flaky test configuration:
# Tests marked with @pytest.mark.flaky(reruns=N, reruns_delay=S) will automatically
# retry N times with S seconds delay between retries when they fail.
# This is used for tests that may have timing issues, network instability, or
# race conditions in success field updates.


def pytest_addoption(parser):
    parser.addoption(
        "--config",
        type=str,
        help="Full toml config",
    )


def pytest_generate_tests(metafunc):
    # Define all CLI arguments we want to support
    cli_args = [
        "config",
    ]

    # Check if the test is marked with @pytest.mark.use_cli_args
    marker = metafunc.definition.get_closest_marker("use_cli_args")
    if marker:
        params = {}

        # Only parametrize the test if it requests matching fixtures
        for arg in cli_args:
            if arg in metafunc.fixturenames:
                option_value = metafunc.config.getoption(f"--{arg}")
                params[arg] = option_value

        # Apply parameterization only if any matching arguments exist
        if params:
            metafunc.parametrize(",".join(params.keys()), [next(iter(params.values()))])
