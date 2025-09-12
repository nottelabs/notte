import base64
import datetime as dt
from typing import Any

import pytest
from notte_core.actions import BrowserAction, ClickAction
from notte_core.browser.observation import Observation, Screenshot
from notte_core.browser.snapshot import SnapshotMetadata, ViewportData
from notte_core.common.config import PlaywrightProxySettings
from notte_core.space import ActionSpace, SpaceCategory
from notte_sdk.types import (
    AgentStatus,
    AgentStatusResponse,
    ObserveResponse,
    ReplayResponse,
    SessionResponse,
    SessionStartRequest,
)
from pydantic import BaseModel, ValidationError


def test_observation_fields_match_response_types():
    """
    Ensure all fields in Observation have corresponding fields in ObserveResponseDict/ObserveResponse.
    This test will fail if a new field is added to Observation but not to the response types.
    """
    # Get all field names from Observation
    observation_fields = Observation.model_fields.keys()

    # Remove internal fields that start with '_'
    observation_fields = {f for f in observation_fields if not f.startswith("_")}

    # Create a sample observation with all fields filled
    sample_data = {
        "metadata": {
            "url": "https://example.com",
            "title": "Test Page",
            "timestamp": dt.datetime.now(),
            "viewport": {
                "scroll_x": 0,
                "scroll_y": 0,
                "viewport_width": 1000,
                "viewport_height": 1000,
                "total_width": 1000,
                "total_height": 1000,
            },
            "tabs": [],
        },
        "screenshot": {"raw": Observation.empty().screenshot.raw},
        "data": {
            "markdown": "test data",
        },
        "progress": {
            "current_step": 0,
            "max_steps": 10,
        },
    }

    # Try to create ObserveResponseDict with these fields
    response_dict = {
        "session": {
            "session_id": "test_session",  # Required by ResponseDict
            "timeout_minutes": 100,
            "created_at": dt.datetime.now(),
            "last_accessed_at": dt.datetime.now(),
            "duration": dt.timedelta(seconds=100),
            "status": "active",
        },
        **sample_data,
        "space": {
            "description": "test space",
            "interaction_actions": [],
            "category": None,
            "browser_actions": BrowserAction.list(),
        },
    }

    # This will raise a type error if any required fields are missing
    response = ObserveResponse.model_validate(response_dict)

    # Check that all Observation fields exist in ObserveResponse
    response_fields = set(response.model_fields.keys())
    missing_fields = observation_fields - response_fields

    assert not missing_fields, f"Fields {missing_fields} exist in Observation but not in ObserveResponse"


class _TestSchema(BaseModel):
    key: str
    value: int


class TestSchemaList(BaseModel):
    items: list[_TestSchema]


def test_observe_response_from_observation():
    obs = Observation(
        metadata=SnapshotMetadata(
            url="https://www.google.com",
            title="Google",
            timestamp=dt.datetime.now(),
            viewport=ViewportData(
                scroll_x=0,
                scroll_y=0,
                viewport_width=1000,
                viewport_height=1000,
                total_width=1000,
                total_height=1000,
            ),
            tabs=[],
        ),
        screenshot=Screenshot(raw=Observation.empty().screenshot.raw),
        space=ActionSpace(
            description="test space",
            category=SpaceCategory.OTHER,
            interaction_actions=[
                ClickAction(
                    id="L0",
                    description="my_test_description_0",
                    category="my_test_category_0",
                ),
                ClickAction(
                    id="L1",
                    description="my_test_description_1",
                    category="my_test_category_1",
                ),
            ],
        ),
    )
    dt_now = dt.datetime.now()
    session = SessionResponse(
        session_id="test_session",
        timeout_minutes=100,
        created_at=dt_now,
        last_accessed_at=dt_now,
        duration=dt.timedelta(seconds=100),
        status="active",
    )

    response = ObserveResponse.from_obs(
        session=session,
        obs=obs,
    )
    assert response.session.session_id == "test_session"
    assert response.session.timeout_minutes == 100
    assert response.session.created_at == dt_now
    assert response.session.last_accessed_at == dt_now
    assert response.session.duration == dt.timedelta(seconds=100)
    assert response.session.status == "active"
    assert response.metadata.title == "Google"
    assert response.metadata.url == "https://www.google.com"
    assert response.screenshot.raw == Observation.empty().screenshot.raw
    assert response.space is not None
    assert response.space.description == "test space"
    assert response.space.category == "other"
    assert obs.space is not None
    assert response.space.interaction_actions == obs.space.interaction_actions


def test_agent_status_response_replay():
    # Test case 1: Base64 encoded string
    sample_webp_data = b"fake_webp_data"
    base64_encoded = base64.b64encode(sample_webp_data).decode("utf-8")
    response = AgentStatusResponse.model_validate(
        {
            "agent_id": "test_agent",
            "created_at": "2024-03-20",
            "session_id": "test_session",
            "status": AgentStatus.active,
            "replay": base64_encoded,
            "task": "test_task",
            "url": "https://www.google.com",
            "replay_start_offset": -1,
            "replay_stop_offset": -1,
        }
    )
    assert response.replay == sample_webp_data

    # Test case 2: Direct bytes input
    response = AgentStatusResponse.model_validate(
        {
            "agent_id": "test_agent",
            "created_at": "2024-03-20",
            "session_id": "test_session",
            "status": AgentStatus.active,
            "replay": sample_webp_data,
            "task": "test_task",
            "url": "https://www.google.com",
            "replay_start_offset": -1,
            "replay_stop_offset": -1,
        }
    )
    assert response.replay == sample_webp_data

    # Test case 3: None input
    response = AgentStatusResponse.model_validate(
        {
            "agent_id": "test_agent",
            "created_at": "2024-03-20",
            "session_id": "test_session",
            "status": AgentStatus.active,
            "replay": None,
            "task": "test_task",
            "url": "https://www.google.com",
            "replay_start_offset": -1,
            "replay_stop_offset": -1,
        }
    )
    assert response.replay is None

    # Test case 4: Invalid input
    with pytest.raises(ValueError, match="replay must be a bytes or a base64 encoded string"):
        _ = AgentStatusResponse.model_validate(
            {
                "agent_id": "test_agent",
                "created_at": "2024-03-20",
                "session_id": "test_session",
                "status": AgentStatus.active,
                "replay": 123,
                "task": "test_task",
                "url": "https://www.google.com",
                "replay_start_offset": -1,
                "replay_stop_offset": -1,
            }
        )


def test_replay_response_from_replay():
    replay = ReplayResponse(
        replay=b"fake_replay_data",
    )
    assert replay.replay == b"fake_replay_data"
    encoded_replay = "ZmFrZV9yZXBsYXlfZGF0YQ=="
    # this should not raise an error
    assert replay.model_dump() == {"replay": encoded_replay}
    assert replay.model_dump_json() == f'{{"replay":"{encoded_replay}"}}'


@pytest.mark.parametrize("proxies", [True, [{"type": "notte"}], [{"type": "notte", "geolocation": {"country": "us"}}]])
def test_default_proxy_settings_notte(proxies: list[dict[str, Any]]):
    proxy_settings = SessionStartRequest.model_validate({"proxies": proxies})
    with pytest.raises(NotImplementedError, match="Notte proxy only supported in cloud"):
        proxy_settings.playwright_proxy


def test_default_proxy_settings_external():
    proxy_settings = SessionStartRequest.model_validate(
        {"proxies": [{"type": "external", "server": "http://localhost:8080"}]}
    )
    assert proxy_settings.playwright_proxy == PlaywrightProxySettings(
        server="http://localhost:8080", bypass=None, username=None, password=None
    )


@pytest.mark.parametrize("proxies", [False, []])
def test_default_proxy_should_be_disabled(proxies: list[dict[str, Any]]):
    proxy_settings = SessionStartRequest.model_validate({"proxies": proxies})
    assert proxy_settings.playwright_proxy is None


def test_multiple_proxies_should_raise_error():
    with pytest.raises(ValueError, match="Multiple proxies are not supported yet. Got 2 proxies."):
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte"}, {"type": "notte"}]})
        _ = request.playwright_proxy


def test_unknown_proxy_type_should_raise_error():
    with pytest.raises(ValidationError, match="validation errors for SessionStartRequest"):
        _ = SessionStartRequest.model_validate({"proxies": [{"type": "unknown"}]})
