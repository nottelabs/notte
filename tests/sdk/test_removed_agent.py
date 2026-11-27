import pytest
from notte_sdk import AsyncNotteClient, NotteClient


def test_agent_raises_with_act_loop_snippet() -> None:
    client = NotteClient(api_key="test-api-key")
    with pytest.raises(AttributeError, match="client.Agent was removed") as exc_info:
        _ = client.Agent
    message = str(exc_info.value)
    assert "result = session.act(" in message
    assert "https://docs.notte.cc/features/sessions/act" in message
    assert not hasattr(client, "Agent")


def test_async_agent_raises_with_act_loop_snippet() -> None:
    client = AsyncNotteClient(api_key="test-api-key")
    with pytest.raises(AttributeError, match="client.Agent was removed") as exc_info:
        _ = client.Agent
    message = str(exc_info.value)
    assert "await session.act(" in message
    assert "https://docs.notte.cc/features/sessions/act" in message
