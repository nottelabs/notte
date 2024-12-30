import datetime as dt
from dataclasses import fields

from notte.actions.base import Action
from notte.actions.space import ActionSpace, SpaceCategory
from notte.browser.observation import Observation
from notte.sdk.types import ActionSpaceResponse, ObserveResponse


def test_observation_fields_match_response_types():
    """
    Ensure all fields in Observation have corresponding fields in ObserveResponseDict/ObserveResponse.
    This test will fail if a new field is added to Observation but not to the response types.
    """
    # Get all field names from Observation
    observation_fields = {field.name for field in fields(Observation)}

    # Remove internal fields that start with '_'
    observation_fields = {f for f in observation_fields if not f.startswith("_")}

    # Create a sample observation with all fields filled
    sample_data = {
        "url": "https://example.com",
        "title": "Test Page",
        "timestamp": dt.datetime.now(),
        "screenshot": b"fake_screenshot",
        "data": "test data",
    }

    # Try to create ObserveResponseDict with these fields
    response_dict = {
        **sample_data,
        "session_id": "test_session",  # Required by ResponseDict
        "space": {"description": "test space", "actions": [], "category": None},
    }

    # This will raise a type error if any required fields are missing
    response = ObserveResponse.model_validate(response_dict)

    # Check that all Observation fields exist in ObserveResponse
    response_fields = set(response.model_fields.keys())
    missing_fields = observation_fields - response_fields

    assert not missing_fields, f"Fields {missing_fields} exist in Observation but not in ObserveResponse"


def test_action_space_fields_match_response_types():
    """
    Ensure all fields in ActionSpace have corresponding fields in ActionSpaceResponseDict/ActionSpaceResponse.
    This test will fail if a new field is added to ActionSpace but not to the response types.
    """
    # Get all field names from ActionSpace
    space_fields = {field.name for field in fields(ActionSpace)}

    # Remove internal fields that start with '_' and known exclusions
    excluded_fields = {"_embeddings", "_actions"}  # _actions is 'actions' in the response types
    space_fields = {f for f in space_fields if not f.startswith("_") and f not in excluded_fields}
    space_fields.add("actions")  # Add back 'actions' without underscore

    # Create a sample space with all fields filled
    sample_data = {"description": "test space", "actions": [], "category": "homepage"}

    # Try to create ActionSpaceResponseDict with these fields
    response_dict = sample_data

    # This will raise a type error if any required fields are missing
    response = ActionSpaceResponse.model_validate(response_dict)

    # Check that all ActionSpace fields exist in ActionSpaceResponse
    response_fields = set(response.model_fields.keys())
    missing_fields = space_fields - response_fields

    assert not missing_fields, f"Fields {missing_fields} exist in ActionSpace but not in ActionSpaceResponse"


def test_observe_response_from_observation():
    obs = Observation(
        url="https://www.google.com",
        title="Google",
        timestamp=dt.datetime.now(),
        screenshot=b"fake_screenshot",
        data="test data",
        _space=ActionSpace(
            description="test space",
            category=SpaceCategory.OTHER,
            _actions=[
                Action(
                    id="my_test_id_0",
                    description="my_test_description_0",
                    category="my_test_category_0",
                ),
                Action(
                    id="my_test_id_1",
                    description="my_test_description_1",
                    category="my_test_category_1",
                ),
            ],
        ),
    )

    response = ObserveResponse.from_obs(
        session_id="test_session",
        obs=obs,
    )
    assert response.session_id == "test_session"
    assert response.title == "Google"
    assert response.url == "https://www.google.com"
    assert response.screenshot == b"fake_screenshot"
    assert response.data == "test data"
    assert response.space is not None
    assert response.space.description == "test space"
    assert response.space.category == "other"
    assert response.space.actions == obs.space.actions()
