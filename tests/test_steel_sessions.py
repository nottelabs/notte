from unittest.mock import Mock, patch

import pytest
from notte_integrations.sessions.steel import SteelSessionsManager


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
