from base64 import b64encode
from typing import TypedDict

from pydantic import BaseModel

from notte.actions.base import Action

# ############################################################
# Session Management
# ############################################################


class SessionRequest(BaseModel):
    session_id: str | None = None
    keep_alive: bool = False
    session_timeout: int = 10
    screenshot: bool = True


class SessionResponse(BaseModel):
    session_id: str
    error: str | None = None


class SessionRequestDict(TypedDict, total=False):
    session_id: str | None
    keep_alive: bool
    session_timeout: int
    screenshot: bool


class SessionResponseDict(TypedDict, total=False):
    session_id: str
    error: str | None


# ############################################################
# Main API
# ############################################################


class ObserveRequest(SessionRequest):
    url: str | None = None


class StepRequest(SessionRequest):
    action_id: str
    value: str | None = None
    enter: bool = False


class ObserveResponse(SessionResponse):
    url: str
    actions: list[Action] | None = None
    data: str = ""
    screenshot: bytes | None = None

    class Config:
        json_encoders = {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }


class ObserveRequestDict(SessionRequestDict, total=False):
    url: str | None


class ObserveResponseDict(SessionResponseDict, total=False):
    url: str
    actions: list[Action] | None
    data: str
    screenshot: bytes | None


class StepRequestDict(SessionRequestDict, total=False):
    action_id: str
    value: str | None
    enter: bool
