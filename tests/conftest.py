import os
import time
from pathlib import Path

import notte_core
import pytest

CONFIG_PATH = Path(__file__).parent / "test_notte_config.toml"
notte_core.set_error_mode("developer")

os.environ["NOTTE_CONFIG_PATH"] = str(CONFIG_PATH)


# if we run in Github Actions, we need to disable GPU
if os.getenv("GITHUB_ACTIONS") is not None:
    os.environ["DISABLE_GPU"] = "true"


# pytest-isolate takes over pytest_runtest_protocol and returns True, which
# prevents pytest-rerunfailures from ever seeing failures. This hook runs at
# a higher priority (tryfirst) so it wraps isolate's subprocess execution
# with retry logic for tests marked @pytest.mark.flaky(reruns=N).
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    flaky_marker = item.get_closest_marker("flaky")
    if flaky_marker is None:
        return None  # let pytest-isolate (or default) handle it

    reruns = flaky_marker.kwargs.get("reruns", 0)
    reruns_delay = flaky_marker.kwargs.get("reruns_delay", 0)
    if reruns < 1:
        return None

    from pytest_isolate.plugin import get_isolation_options, run_in_subprocess

    isolate, timeout, mem_limit, cpu_limit, _resource_reqs = get_isolation_options(item)
    if timeout is None and isolate is None and mem_limit is None and cpu_limit is None:
        return None  # not an isolated test, let normal hooks handle it

    wait_delta = float(item.config.getini("wait_delta"))
    ihook = item.ihook

    for attempt in range(1 + reruns):
        ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        reports = run_in_subprocess(item, timeout, mem_limit, cpu_limit, wait_delta)

        call_report = next((r for r in reports if r.when == "call"), None)
        failed = call_report is not None and call_report.failed

        if not failed or attempt == reruns:
            for rep in reports:
                ihook.pytest_runtest_logreport(report=rep)
            ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
            break

        # Log the failure as a rerun before retrying
        for rep in reports:
            if rep.when == "call":
                rep.outcome = "rerun"
            ihook.pytest_runtest_logreport(report=rep)
        ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)

        if reruns_delay > 0:
            time.sleep(reruns_delay)

    return True


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
