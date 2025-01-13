import datetime as dt
from base64 import b64encode
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from notte.actions.base import Action, SpecialAction
from notte.actions.space import ActionSpace
from notte.browser.observation import Observation
from notte.browser.snapshot import SnapshotMetadata
from notte.data.space import DataSpace, ImageData

# ############################################################
# Session Management
# ############################################################

DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES = 5
DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES = 30
DEFAULT_MAX_NB_ACTIONS = 100


class SessionRequestDict(TypedDict, total=False):
    session_id: str | None
    keep_alive: bool
    session_timeout_minutes: int
    screenshot: bool | None


class SessionRequest(BaseModel):
    session_id: Annotated[
        str | None, Field(description="The ID of the session. A new session is created when not provided.")
    ] = None

    keep_alive: Annotated[
        bool, Field(description="If True, the session will not be closed after the operation is completed.")
    ] = False

    session_timeout_minutes: Annotated[
        int,
        Field(
            description="Session timeout in minutes. Cannot exceed the global timeout.",
            gt=0,
            le=DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES,
        ),
    ] = DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES

    screenshot: Annotated[bool | None, Field(description="Whether to include a screenshot in the response.")] = None

    def __post_init__(self):
        if self.session_timeout_minutes > DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES:
            raise ValueError(
                (
                    "Session timeout cannot be greater than global timeout: "
                    f"{self.session_timeout_minutes} > {DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES}"
                )
            )


class SessionResponse(BaseModel):
    session_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the session (created or existing). "
                "Use this ID to interact with the session for the next operation."
            )
        ),
    ]
    timeout_minutes: Annotated[
        int, Field(description="Session timeout in minutes. Will timeout if now() > last access time + timeout_minutes")
    ]
    created_at: Annotated[dt.datetime, Field(description="Session creation time")]
    last_accessed_at: Annotated[dt.datetime, Field(description="Last access time")]
    duration: Annotated[dt.timedelta, Field(description="Session duration")]
    status: Annotated[Literal["active", "closed", "error", "timed_out"], Field(description="Session status")]
    # TODO: discuss if this is the best way to handle errors
    error: Annotated[str | None, Field(description="Error message if the operation failed to complete")] = None


class SessionResponseDict(TypedDict, total=False):
    session_id: str
    timeout_minutes: int
    created_at: dt.datetime
    last_accessed_at: dt.datetime
    duration: dt.timedelta
    status: Literal["active", "closed", "error", "timed_out"]
    error: str | None


# ############################################################
# Main API
# ############################################################


class PaginationObserveRequestDict(TypedDict, total=False):
    min_nb_actions: int | None
    max_nb_actions: int


class PaginationObserveRequest(BaseModel):
    min_nb_actions: Annotated[
        int | None,
        Field(
            description=(
                "The minimum number of actions to list before stopping. "
                "If not provided, the listing will continue until the maximum number of actions is reached."
            ),
        ),
    ] = None
    max_nb_actions: Annotated[
        int,
        Field(
            description=(
                "The maximum number of actions to list after which the listing will stop. "
                "Used when min_nb_actions is not provided."
            ),
        ),
    ] = DEFAULT_MAX_NB_ACTIONS


class ObserveRequest(SessionRequest, PaginationObserveRequest):
    url: Annotated[str | None, Field(description="The URL to observe. If not provided, uses the current page URL.")] = (
        None
    )


class ObserveRequestDict(SessionRequestDict, PaginationObserveRequestDict, total=False):
    url: str | None


class ScrapeRequestDict(SessionRequestDict, total=False):
    scrape_images: bool
    only_main_content: bool


class ScrapeRequest(ObserveRequest):
    scrape_images: Annotated[
        bool, Field(description="Whether to scrape images from the page. Images are not scraped by default.")
    ] = False

    only_main_content: Annotated[
        bool,
        Field(
            description=(
                "Whether to only scrape the main content of the page. " "If True, navbars, footers, etc. are excluded."
            ),
        ),
    ] = True


class StepRequest(SessionRequest, PaginationObserveRequest):
    action_id: Annotated[str, Field(description="The ID of the action to execute")]

    value: Annotated[str | None, Field(description="The value to input for form actions")] = None

    enter: Annotated[bool | None, Field(description="Whether to press enter after inputting the value")] = None


class StepRequestDict(SessionRequestDict, PaginationObserveRequestDict, total=False):
    action_id: str
    value: str | None
    enter: bool | None


class ActionSpaceResponse(BaseModel):
    markdown: Annotated[str | None, Field(description="Markdown representation of the action space")] = None
    description: Annotated[str, Field(description="Human-readable description of the current web page")]

    actions: Annotated[list[Action], Field(description="List of available actions in the current state")]
    special_actions: Annotated[list[SpecialAction], Field(description="List of special actions, i.e browser actions")]

    category: Annotated[
        str | None, Field(description="Category of the action space (e.g., 'homepage', 'search-results', 'item)")
    ] = None

    @staticmethod
    def from_space(space: ActionSpace | None) -> "ActionSpaceResponse | None":
        if space is None:
            return None

        return ActionSpaceResponse(
            markdown=space.markdown(),
            description=space.description,
            category=space.category.value if space.category is not None else None,
            actions=space.actions(),
            special_actions=space.special_actions(),
        )


class DataSpaceResponse(BaseModel):
    markdown: Annotated[str | None, Field(description="Markdown representation of the extracted data")] = None

    images: Annotated[
        list[ImageData] | None, Field(description="List of images extracted from the page (ID and download link)")
    ] = None

    structured: Annotated[
        list[dict[str, Any]] | None, Field(description="Structured data extracted from the page in JSON format")
    ] = None

    @staticmethod
    def from_data(data: DataSpace | None) -> "DataSpaceResponse | None":
        if data is None:
            return None
        return DataSpaceResponse(
            markdown=data.markdown,
            images=data.images,
            structured=data.structured,
        )


class ObserveResponse(BaseModel):
    session: Annotated[SessionResponse, Field(description="Browser session information")]
    metadata: Annotated[
        SnapshotMetadata, Field(description="Metadata of the current page, i.e url, page title, snapshot timestamp.")
    ]

    screenshot: Annotated[bytes | None, Field(description="Base64 encoded screenshot of the current page")] = None

    data: Annotated[DataSpaceResponse | None, Field(description="Extracted data from the page")] = None

    space: Annotated[ActionSpaceResponse | None, Field(description="Available actions in the current state")] = None

    model_config = {
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @staticmethod
    def from_obs(
        obs: Observation,
        session: SessionResponse,
    ) -> "ObserveResponse":
        return ObserveResponse(
            session=session,
            metadata=obs.metadata,
            screenshot=obs.screenshot,
            data=DataSpaceResponse.from_data(obs.data),
            space=ActionSpaceResponse.from_space(obs.space if obs.has_space() else None),
        )
