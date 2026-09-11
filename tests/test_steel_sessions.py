from unittest.mock import Mock, PropertyMock, patch

import pytest
from notte_integrations.sessions.cdp_session import CDPSession
from notte_integrations.sessions.steel import SteelSessionsManager
from notte_sdk import NotteClient


@pytest.mark.parametrize("region,payload", [(None, {}), ("lax", {"region": "lax"})])
def test_steel_session_region_selection(region: str | None, payload: dict[str, str]):
    manager = SteelSessionsManager(steel_api_key="test-key", region=region)
    response = Mock()
    response.json.return_value = {"id": "steel-session-id"}
    with patch("notte_integrations.sessions.steel.requests.post", return_value=response) as post:
        session = manager.create_session_cdp(Mock())

    assert session.session_id == "steel-session-id"
    assert post.call_args.kwargs["json"] == payload
    assert post.call_args.kwargs["timeout"] == 60
    response.raise_for_status.assert_called_once()


@pytest.mark.parametrize("failure_stage", ["construct", "enter"])
def test_steel_browser_is_released_when_notte_session_start_fails(failure_stage: str):
    client = NotteClient(api_key="test-key")
    manager = SteelSessionsManager(steel_api_key="test-key", client=client)
    factory = Mock()
    if failure_stage == "construct":
        factory.side_effect = RuntimeError("Cannot start session")
    else:
        factory.return_value = Mock(__enter__=Mock(side_effect=RuntimeError("Cannot start session")))
    with (
        patch.object(NotteClient, "Session", new_callable=PropertyMock, return_value=factory),
        patch.object(
            SteelSessionsManager,
            "create_session_cdp",
            return_value=CDPSession(session_id="steel-session-id", cdp_url="ws://localhost:9222"),
        ),
        patch.object(SteelSessionsManager, "close_session_cdp", return_value=True) as release,
        pytest.raises(RuntimeError, match="Cannot start session"),
    ):
        manager.__enter__()
    factory.assert_called_once_with(cdp_url="ws://localhost:9222", proxies=False)
    release.assert_called_once_with("steel-session-id")
