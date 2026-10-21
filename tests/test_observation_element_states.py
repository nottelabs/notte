"""`Observation.element_states` / `fingerprint`: optional fields of the observe response, compatible both ways."""

import datetime as dt
import json

import pytest
from notte_core.actions import ClickAction, FillAction
from notte_core.element_state import ElementState, SelectOption
from notte_core.observation import Observation
from notte_core.snapshot import SnapshotMetadata, ViewportData
from notte_core.space import ActionSpace
from pydantic import BaseModel

STATES = {
    "I1": ElementState(value="ada"),
    "I2": ElementState(
        value="en",
        options=(SelectOption(value="en", label="English", selected=True), SelectOption(value="fr", label="French")),
    ),
    "I3": ElementState(filled=True),
}


def _observation(**fields: object) -> Observation:
    now = dt.datetime.now(dt.timezone.utc)
    return Observation(
        metadata=SnapshotMetadata(
            title="Search",
            url="https://search.test/",
            viewport=ViewportData(
                scroll_x=0, scroll_y=0, viewport_width=1280, viewport_height=720, total_width=1280, total_height=720
            ),
            tabs=[],
        ),
        screenshot=b"",
        space=ActionSpace(
            description='I1[:]<input name="q"></input>\nB1[:]<button>Search</button>',
            interaction_actions=[FillAction(id="I1", value="<sample_value>"), ClickAction(id="B1")],
        ),
        started_at=now,
        ended_at=now,
        **fields,  # pyright: ignore[reportArgumentType]
    )


@pytest.mark.parametrize("by_alias", [False, True])
def test_element_states_round_trip(by_alias: bool) -> None:
    observation = _observation(element_states=STATES, fingerprint="fp")
    parsed = Observation.model_validate_json(observation.model_dump_json(by_alias=by_alias))
    assert parsed.element_states == STATES and parsed.fingerprint == "fp"


def test_a_payload_without_the_fields_parses() -> None:
    # an observe response from a server that does not report the state
    payload = json.loads(_observation().model_dump_json())
    del payload["element_states"], payload["fingerprint"]
    parsed = Observation.model_validate(payload)
    assert parsed.element_states is None and parsed.fingerprint is None


def test_an_older_client_ignores_the_fields() -> None:
    class OlderObservation(BaseModel):
        metadata: SnapshotMetadata
        space: ActionSpace

    parsed = OlderObservation.model_validate_json(
        _observation(element_states=STATES, fingerprint="fp").model_dump_json()
    )
    assert [a.id for a in parsed.space.interaction_actions] == ["I1", "B1"]


def test_a_password_state_never_carries_a_value() -> None:
    payload = json.loads(_observation(element_states=STATES).model_dump_json())
    assert payload["element_states"]["I3"]["filled"] is True and payload["element_states"]["I3"]["value"] is None
