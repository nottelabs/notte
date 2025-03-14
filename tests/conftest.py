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
