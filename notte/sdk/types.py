import datetime as dt
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from notte.actions.base import Action, BrowserAction
from notte.browser.observation import Observation, TrajectoryProgress
from notte.browser.snapshot import SnapshotMetadata
from notte.controller.space import BaseActionSpace
from notte.data.space import DataSpace

# ############################################################
# Session Management
# ############################################################

DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES = 5
DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES = 30
DEFAULT_MAX_NB_ACTIONS = 100
DEFAULT_MAX_NB_STEPS = 20


class SessionRequestDict(TypedDict, total=False):
    session_id: str | None
    keep_alive: bool
    session_timeout_minutes: int
    screenshot: bool | None
    max_steps: int


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

    max_steps: Annotated[
        int | None,
        Field(
            gt=0,
            description="Maximum number of steps in the trajectory. An error will be raised if this limit is reached.",
        ),
    ] = DEFAULT_MAX_NB_STEPS

    def __post_init__(self):
        if self.session_timeout_minutes > DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES:
            raise ValueError(
                "Session timeout cannot be greater than global timeout: "
                f"{self.session_timeout_minutes} > {DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES}"
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


class PaginationParams(BaseModel):
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


class ObserveRequest(SessionRequest, PaginationParams):
    url: Annotated[str | None, Field(description="The URL to observe. If not provided, uses the current page URL.")] = (
        None
    )


class ObserveRequestDict(SessionRequestDict, PaginationObserveRequestDict, total=False):
    url: str | None


class ScrapeRequestDict(SessionRequestDict, total=False):
    scrape_images: bool
    scrape_links: bool
    only_main_content: bool
    response_format: type[BaseModel] | None
    instructions: str | None


class ScrapeParams(BaseModel):
    scrape_images: Annotated[
        bool, Field(description="Whether to scrape images from the page. Images are not scraped by default.")
    ] = False

    scrape_links: Annotated[
        bool, Field(description="Whether to scrape links from the page. Links are scraped by default.")
    ] = True

    only_main_content: Annotated[
        bool,
        Field(
            description=(
                "Whether to only scrape the main content of the page. If True, navbars, footers, etc. are excluded."
            ),
        ),
    ] = True

    response_format: Annotated[
        type[BaseModel] | None, Field(description="The response format to use for the scrape.")
    ] = None
    instructions: Annotated[str | None, Field(description="The instructions to use for the scrape.")] = None

    def requires_schema(self) -> bool:
        return self.response_format is not None or self.instructions is not None


class ScrapeRequest(ObserveRequest, ScrapeParams):
    pass


class StepRequest(SessionRequest, PaginationParams):
    action_id: Annotated[str, Field(description="The ID of the action to execute")]

    value: Annotated[str | None, Field(description="The value to input for form actions")] = None

    enter: Annotated[bool | None, Field(description="Whether to press enter after inputting the value")] = None


class StepRequestDict(SessionRequestDict, PaginationObserveRequestDict, total=False):
    action_id: str
    value: str | None
    enter: bool | None


class ActionSpaceResponse(BaseModel):
    markdown: Annotated[str | None, Field(description="Markdown representation of the action space")] = None
    actions: Annotated[Sequence[Action], Field(description="List of available actions in the current state")]
    browser_actions: Annotated[
        Sequence[BrowserAction], Field(description="List of special actions, i.e browser actions")
    ]
    # TODO: ActionSpaceResponse should be a subclass of ActionSpace
    description: str
    category: str | None = None

    @staticmethod
    def from_space(space: BaseActionSpace | None) -> "ActionSpaceResponse | None":
        if space is None:
            return None

        return ActionSpaceResponse(
            markdown=space.markdown(),
            description=space.description,
            category=space.category,
            actions=space.actions(),  # type: ignore
            browser_actions=space.browser_actions(),  # type: ignore
        )


class ObserveResponse(BaseModel):
    session: Annotated[SessionResponse, Field(description="Browser session information")]
    space: Annotated[ActionSpaceResponse | None, Field(description="Available actions in the current state")] = None
    metadata: SnapshotMetadata
    screenshot: bytes | None
    data: DataSpace | None
    progress: TrajectoryProgress | None

    @staticmethod
    def from_obs(
        obs: Observation,
        session: SessionResponse,
    ) -> "ObserveResponse":
        return ObserveResponse(
            session=session,
            metadata=obs.metadata,
            screenshot=obs.screenshot,
            data=obs.data,
            space=ActionSpaceResponse.from_space(obs.space),
            progress=obs.progress,
        )
