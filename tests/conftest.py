import os
from pathlib import Path

import notte_core

CONFIG_PATH = Path(__file__).parent / "test_notte_config.toml"
notte_core.set_error_mode("developer")

os.environ["NOTTE_CONFIG_PATH"] = str(CONFIG_PATH)


# if we run in Github Actions, we need to disable GPU
if os.getenv("GITHUB_ACTIONS") is not None:
    os.environ["DISABLE_GPU"] = "true"


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
