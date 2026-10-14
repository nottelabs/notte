from unittest.mock import patch

import pytest
from notte_agent.falco.agent import FalcoAgent
from notte_browser.session import NotteSession
from notte_core.actions import CompletionAction, FillAction
from notte_core.credentials import EMAIL, MFA, PASSWORD
from notte_core.errors.actions import NoCredentialsFoundError
from notte_core.errors.processing import (
    CredentialFieldValidationError,
    InvalidPlaceholderError,
    MissingCredentialFieldError,
)

from tests.agent.test_consistent_trajectory import MockLLMEngine, MockValidator, create_agent_step_response
from tests.mock.mock_vault import MockVault
from tests.test_vault_credential_redaction import capture_logs

LOGIN_PAGE = """
<form>
    <label id="pw-label" for="pw">Password</label>
    <input id="pw" type="password" />
</form>
"""
LOGIN_URL = "https://login.example.test/"


@pytest.mark.asyncio
async def test_agent_recovers_from_password_placeholder_on_label() -> None:
    """A credential fill on the wrong element is reported as a failed step instead of aborting
    the run, and the literal placeholder is never typed into the page."""
    vault = MockVault({LOGIN_URL: {"password": "s3cr3t"}})
    mock_llm = MockLLMEngine(
        [
            create_agent_step_response(action=FillAction(selector="#pw-label", value=PASSWORD)),
            create_agent_step_response(action=FillAction(selector="#pw", value=PASSWORD)),
            create_agent_step_response(action=CompletionAction(success=True, answer="Password filled")),
        ]
    )

    async with NotteSession(headless=True) as session:
        await session.window.page.route(
            f"{LOGIN_URL}**", lambda route: route.fulfill(status=200, content_type="text/html", body=LOGIN_PAGE)
        )
        _ = await session.aexecute(type="goto", url=LOGIN_URL, raise_on_failure=True)
        agent = FalcoAgent(session=session, vault=vault, max_steps=5)

        with patch.object(agent, "llm", mock_llm), patch.object(agent, "validator", MockValidator()):
            response = await agent.arun(task="Fill in the password")

        assert response.success is True
        failed = [r for r in agent.trajectory.execution_results() if not r.success]
        assert len(failed) == 1
        assert isinstance(failed[0].exception, CredentialFieldValidationError)
        assert "s3cr3t" not in failed[0].message
        assert await session.window.page.input_value("#pw") == "s3cr3t"


FULL_LOGIN_PAGE = """
<form>
    <input id="email" type="email" />
    <input id="pw" type="password" />
    <input id="otp" type="text" autocomplete="one-time-code" />
</form>
"""
SECRET_EMAIL = "agent-canary-4d1e@example.net"  # pragma: allowlist secret
SECRET_PASSWORD = "Agent-Canary-Pw-0b7f9"  # pragma: allowlist secret


async def open_login_page(session: NotteSession) -> None:
    await session.window.page.route(
        f"{LOGIN_URL}**", lambda route: route.fulfill(status=200, content_type="text/html", body=FULL_LOGIN_PAGE)
    )
    _ = await session.aexecute(type="goto", url=LOGIN_URL, raise_on_failure=True)


def assert_no_secret(texts: list[str]) -> None:
    for text in texts:
        assert SECRET_EMAIL not in text
        assert SECRET_PASSWORD not in text


@pytest.mark.asyncio
async def test_agent_vault_fill_does_not_leak_secret() -> None:
    """The agent and its session share the vault (as `notte.Agent` sets it up): the credentials are replaced
    once, and the secret values never show up in logs or in the trajectory."""
    vault = MockVault({LOGIN_URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    mock_llm = MockLLMEngine(
        [
            create_agent_step_response(action=FillAction(selector="#email", value=EMAIL)),
            create_agent_step_response(action=FillAction(selector="#pw", value=PASSWORD)),
            create_agent_step_response(action=CompletionAction(success=True, answer="Logged in")),
        ]
    )

    with capture_logs() as logs:
        async with NotteSession(headless=True, vault=vault) as session:
            await open_login_page(session)
            agent = FalcoAgent(session=session, vault=vault, max_steps=5)

            with patch.object(agent, "llm", mock_llm), patch.object(agent, "validator", MockValidator()):
                response = await agent.arun(task="Log in")

            assert response.success is True
            results = list(agent.trajectory.execution_results())
            assert all(r.success for r in results)
            assert await session.window.page.input_value("#email") == SECRET_EMAIL
            assert await session.window.page.input_value("#pw") == SECRET_PASSWORD
            assert_no_secret([r.message for r in results] + [r.model_dump_json() for r in results] + [response.answer])
    assert len(logs) > 0
    assert_no_secret(logs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("creds_url", "selector", "value", "error_type"),
    [
        # no credentials for the current domain (e.g. after an SSO redirect)
        ("https://other.example.test/", "#email", EMAIL, NoCredentialsFoundError),
        # the field is not stored in the vault
        (LOGIN_URL, "#otp", MFA, MissingCredentialFieldError),
        # the agent wrote a near-miss placeholder
        (LOGIN_URL, "#pw", PASSWORD + "1", InvalidPlaceholderError),
    ],
)
async def test_agent_records_failed_step_when_placeholder_cannot_be_replaced(
    creds_url: str, selector: str, value: str, error_type: type[Exception]
) -> None:
    vault = MockVault({creds_url: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    mock_llm = MockLLMEngine(
        [
            create_agent_step_response(action=FillAction(selector=selector, value=value)),
            create_agent_step_response(action=CompletionAction(success=True, answer="Gave up on the credential")),
        ]
    )

    with capture_logs() as logs:
        async with NotteSession(headless=True, vault=vault) as session:
            await open_login_page(session)
            agent = FalcoAgent(session=session, vault=vault, max_steps=5)

            with patch.object(agent, "llm", mock_llm), patch.object(agent, "validator", MockValidator()):
                response = await agent.arun(task="Log in")

            # the run continues after the failed step
            assert response.success is True
            failed = [r for r in agent.trajectory.execution_results() if not r.success]
            assert len(failed) == 1
            assert isinstance(failed[0].exception, error_type)
            # the literal placeholder is never typed into the page
            assert await session.window.page.input_value(selector) == ""
            assert_no_secret([failed[0].message])
    assert_no_secret(logs)
