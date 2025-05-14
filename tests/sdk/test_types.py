import base64
import datetime as dt

import pytest
from notte_core.actions.base import BrowserAction
from notte_core.actions.percieved import PerceivedAction
from notte_core.actions.space import ActionSpace, SpaceCategory
from notte_core.browser.observation import Observation
from notte_core.browser.snapshot import SnapshotMetadata, ViewportData
from notte_core.data.space import DataSpace, ImageData, StructuredData
from notte_sdk.types import (
    AgentStatus,
    AgentStatusResponse,
    ObserveResponse,
    ReplayResponse,
    SessionResponse,
)
from pydantic import BaseModel


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
        "screenshot": b"fake_screenshot",
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
            "actions": [],
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


class TestSchema(BaseModel):
    key: str
    value: int


class TestSchemaList(BaseModel):
    items: list[TestSchema]


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
        screenshot=b"fake_screenshot",
        data=DataSpace(
            markdown="test data",
            images=[
                ImageData(id="F1", url="https://www.google.com/image1.jpg"),
                ImageData(id="F2", url="https://www.google.com/image2.jpg"),
            ],
            structured=StructuredData(
                success=True,
                data=TestSchemaList.model_validate({"items": [{"key": "A", "value": 1}, {"key": "B", "value": 2}]}),
            ),
        ),
        space=ActionSpace(
            description="test space",
            category=SpaceCategory.OTHER,
            interaction_actions=[
                PerceivedAction(
                    id="L0",
                    description="my_test_description_0",
                    category="my_test_category_0",
                ),
                PerceivedAction(
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
    assert response.screenshot == b"fake_screenshot"
    assert response.data is not None
    assert response.data.markdown == "test data"
    assert response.space is not None
    assert response.space.description == "test space"
    assert response.space.category == "other"
    assert obs.space is not None
    assert response.space.actions == obs.space.actions


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
