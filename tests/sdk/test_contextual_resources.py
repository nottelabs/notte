import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.endpoints.sessions import get_context_session_id
from notte_sdk.endpoints.vaults import get_context_vault_id


@pytest.fixture
def notte() -> NotteClient:
    _ = load_dotenv()
    return NotteClient()


def test_start_agent_with_contextual_session_should_raise_error(notte: NotteClient):
    assert get_context_session_id() is None
    with notte.Session() as session:
        assert get_context_session_id() is not None
        assert get_context_session_id() == session.session_id
        with pytest.raises(ValueError):
            # should fail to prevent unexpected behavior
            _ = notte.Agent()
        # should not fail
        _ = notte.Agent(raise_on_existing_contextual_session=False)
        # should not fail
        _ = notte.Agent(session=session)
    assert get_context_session_id() is None

    # outside of context should work correctly
    _ = notte.Agent()


def test_start_agent_with_contextual_vault_should_raise_error(notte: NotteClient):
    assert get_context_vault_id() is None
    with notte.Vault() as vault:
        assert get_context_vault_id() is not None
        assert get_context_vault_id() == vault.vault_id
        with pytest.raises(ValueError):
            # should fail to prevent unexpected behavior
            _ = notte.Agent()
        # should not fail
        _ = notte.Agent(raise_on_existing_contextual_vault=False)
        # should not fail
        _ = notte.Agent(vault=vault)
    assert get_context_vault_id() is None

    # outside of context should work correctly
    _ = notte.Agent()
