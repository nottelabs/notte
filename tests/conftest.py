def pytest_addoption(parser):
    parser.addoption(
        "--agent_llm", action="store", default="cerebras/llama-3.3-70b", help="LLM model to use for the reasoning agent"
    )
    parser.addoption("--n_jobs", action="store", type=int, default=2, help="Number of parallel jobs to run")
    parser.addoption(
        "--include_screenshots", action="store", type=str, default="false", help="Pass screeshots to agent"
    )
    parser.addoption(
        "--history_type", action="store", type=str, default="short_observations_with_short_data", help="Type of history"
    )
    parser.addoption("--tries_per_task", action="store", type=int, default=3, help="How many tries per task")


def pytest_generate_tests(metafunc):
    # Define all CLI arguments we want to support
    cli_args = ["agent_llm", "n_jobs", "include_screenshots", "history_type", "tries_per_task"]

    # Check if the test is marked with @pytest.mark.use_cli_args
    marker = metafunc.definition.get_closest_marker("use_cli_args")
    if marker:
        params = {}

        # Only parametrize the test if it requests matching fixtures
        for arg in cli_args:
            if arg in metafunc.fixturenames:
                option_value = metafunc.config.getoption(f"--{arg}")

                # boolean handling is hacky
                if arg == "include_screenshots":
                    option_value = (option_value.lower()) == "true"
                params[arg] = option_value

        # Apply parameterization only if any matching arguments exist
        if params:
            metafunc.parametrize(",".join(params.keys()), [tuple(params.values())])
