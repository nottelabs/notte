from unittest.mock import patch

import pytest
from notte_agent.falco.agent import FalcoAgent
from notte_browser.session import NotteSession
from notte_core.actions import CompletionAction, FillAction
from notte_core.credentials import PASSWORD
from notte_core.errors.processing import CredentialFieldValidationError

from tests.agent.test_consistent_trajectory import MockLLMEngine, MockValidator, create_agent_step_response
from tests.mock.mock_vault import MockVault

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
