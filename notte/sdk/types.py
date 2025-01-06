import datetime as dt
from base64 import b64encode
from typing import TypedDict

from pydantic import BaseModel

from notte.actions.base import Action
from notte.browser.observation import Observation

# ############################################################
# Session Management
# ############################################################


class SessionRequestDict(TypedDict, total=False):
    session_id: str | None
    keep_alive: bool
    session_timeout: int
    screenshot: bool


class SessionRequest(BaseModel):
    session_id: str | None = None
    keep_alive: bool = True
    session_timeout: int = 10
    screenshot: bool | None = None


class SessionResponse(BaseModel):
    session_id: str
    # TODO: discuss if this is the best way to handle errors
    error: str | None = None


class SessionResponseDict(TypedDict, total=False):
    session_id: str
    error: str | None


# ############################################################
# Main API
# ############################################################


class ObserveRequest(SessionRequest):
    url: str | None = None


class ObserveRequestDict(SessionRequestDict, total=False):
    url: str | None


class StepRequest(SessionRequest):
    action_id: str
    value: str | None = None
    enter: bool | None = None


class StepRequestDict(SessionRequestDict, total=False):
    action_id: str
    value: str | None
    enter: bool | None


class ActionSpaceResponse(BaseModel):
    description: str
    actions: list[Action]
    category: str | None = None


class ObserveResponse(SessionResponse):
    title: str
    url: str
    timestamp: dt.datetime
    screenshot: bytes | None = None
    data: str = ""
    space: ActionSpaceResponse | None = None

    model_config = {
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @staticmethod
    def from_obs(session_id: str, obs: Observation) -> "ObserveResponse":
        return ObserveResponse(
            session_id=session_id,
            title=obs.title,
            url=obs.url,
            timestamp=obs.timestamp,
            screenshot=obs.screenshot,
            data=obs.data,
            space=(
                None
                if not obs.has_space()
                else ActionSpaceResponse(
                    description=obs.space.description,
                    category=None if obs.space.category is None else obs.space.category.value,
                    actions=obs.space.actions(),
                )
            ),
        )


# TODO: Remove this
# class ObserveResponseDict(SessionResponseDict, total=False):
#     title: str
#     url: str
#     timestamp: dt.datetime
#     screenshot: bytes | None
#     data: str
#     space: ActionSpaceResponseDict | None
# class ActionSpaceResponseDict(TypedDict, total=False):
#     description: str
#     actions: list[Action]
#     category: str | None
