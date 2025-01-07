import datetime as dt
from base64 import b64encode
from typing import Any, TypedDict

from pydantic import BaseModel

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.observation import DataSpace, ImageData, Observation

# ############################################################
# Session Management
# ############################################################

DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES = 5
DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES = 30

# class SessionRequest(BaseModel):
#     session_id: Annotated[str | None, Field(default=None, description="The ID of the session. A new session is created when it is not provided. Use observe to interact with existing sessions.")]
#     keep_alive: Annotated[bool, Field(default=False, description="If True, the session will not be closed after the operation is completed (i.e scrape, observe, step).")]
#     session_timeout: Annotated[int, Field(default=DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES)]
#     screenshot: Annotated[bool | None, Field(default=None)]


class SessionRequestDict(TypedDict, total=False):
    session_id: str | None
    keep_alive: bool
    session_timeout: int
    screenshot: bool | None


class SessionRequest(BaseModel):
    session_id: str | None = None
    keep_alive: bool = False
    session_timeout: int = DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES
    screenshot: bool | None = None

    def __post_init__(self):
        if self.session_timeout > DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES:
            raise ValueError(
                f"Session timeout cannot be greater than global timeout: {self.session_timeout} > {DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES}"
            )


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

    @staticmethod
    def from_space(space: ActionSpace | None) -> "ActionSpaceResponse | None":
        if space is None:
            return None

        return ActionSpaceResponse(
            description=space.description,
            category=space.category.value if space.category is not None else None,
            actions=space.actions(),
        )


class DataSpaceResponse(BaseModel):
    markdown: str | None = None
    images: list[ImageData] | None = None
    structured: list[dict[str, Any]] | None = None

    @staticmethod
    def from_data(data: DataSpace | None) -> "DataSpaceResponse | None":
        if data is None:
            return None
        return DataSpaceResponse(
            markdown=data.markdown,
            images=data.images,
            structured=data.structured,
        )


class ObserveResponse(SessionResponse):
    title: str
    url: str
    timestamp: dt.datetime
    screenshot: bytes | None = None
    data: DataSpaceResponse | None = None
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
            data=DataSpaceResponse.from_data(obs.data),
            space=ActionSpaceResponse.from_space(obs.space),
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
