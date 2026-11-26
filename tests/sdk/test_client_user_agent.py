import pytest
from notte_core import __version__ as notte_core_version
from notte_sdk.client import NotteClient
from notte_sdk.client_info import client_user_agent

from tests.sdk.test_generated_endpoints import PROFILE, SERVER, fake

_GITHUB = ("GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")


@pytest.fixture
def no_github(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in _GITHUB:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_the_user_agent_names_the_sdk_outside_ci(no_github: pytest.MonkeyPatch) -> None:
    agent = client_user_agent()
    assert agent.startswith(f"notte-sdk-python/{notte_core_version} (python ")
    assert "github-actions" not in agent


def test_the_user_agent_names_the_github_actions_job(no_github: pytest.MonkeyPatch) -> None:
    no_github.setenv("GITHUB_ACTIONS", "true")
    no_github.setenv("GITHUB_REPOSITORY", "acme/shop")
    no_github.setenv("GITHUB_RUN_ID", "123456")
    no_github.setenv("GITHUB_RUN_ATTEMPT", "2")
    no_github.setenv("GITHUB_JOB", "e2e tests\r\nX-Injected: 1")
    agent = client_user_agent()
    assert agent.endswith(" github-actions (repo=acme/shop; run=123456/2; job=e2e_tests__X-Injected__1)")


def test_api_requests_send_the_user_agent(no_github: pytest.MonkeyPatch) -> None:
    no_github.setattr("notte_sdk.endpoints.base.BaseClient.check_and_warn_version_mismatch", lambda _: None)
    no_github.setenv("GITHUB_ACTIONS", "true")
    no_github.setenv("GITHUB_REPOSITORY", "acme/shop")
    session = fake(no_github, PROFILE)
    client = NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret
    _ = client.profiles.create()
    sent = session.requests[0].headers["user-agent"]
    assert sent == client_user_agent()
    assert sent.endswith(" github-actions (repo=acme/shop)")
