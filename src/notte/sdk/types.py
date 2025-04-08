import datetime as dt
import json
from base64 import b64decode, b64encode
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Generic, Literal, Required, TypeVar

from patchright.async_api import ProxySettings as PlaywrightProxySettings
from pydantic import BaseModel, Field, create_model, field_validator, model_validator
from typing_extensions import TypedDict, override

from notte.actions.base import Action, BrowserAction
from notte.browser.observation import Observation, TrajectoryProgress
from notte.browser.snapshot import SnapshotMetadata, TabsData
from notte.controller.actions import BaseAction
from notte.controller.space import BaseActionSpace
from notte.data.space import DataSpace
from notte.llms.engine import LlmModel

# ############################################################
# Session Management
# ############################################################

DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES = 3
DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES = 30
DEFAULT_MAX_NB_ACTIONS = 100
DEFAULT_MAX_NB_STEPS = 20


class BrowserType(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"


class ProxyGeolocation(BaseModel):
    """
    Geolocation settings for the proxy.
    E.g. "New York, NY, US"
    """

    city: str
    state: str
    country: str


class ProxyType(StrEnum):
    NOTTE = "notte"
    EXTERNAL = "external"


class ProxySettings(BaseModel):
    type: ProxyType
    server: str | None
    bypass: str | None
    username: str | None
    password: str | None
    # TODO: enable geolocation later on
    # geolocation: ProxyGeolocation | None

    @field_validator("server")
    @classmethod
    def validate_server(cls, v: str | None, info: Any) -> str | None:
        if info.data.get("type") == ProxyType.EXTERNAL and v is None:
            raise ValueError("Server is required for external proxy type")
        return v

    def to_playwright(self) -> PlaywrightProxySettings:
        if self.server is None:
            raise ValueError("Proxy server is required")
        return PlaywrightProxySettings(
            server=self.server,
            bypass=self.bypass,
            username=self.username,
            password=self.password,
        )


class Cookie(BaseModel):
    name: str
    domain: str
    path: str
    httpOnly: bool
    expirationDate: float | None = None
    hostOnly: bool | None = None
    sameSite: str | None = None
    secure: bool | None = None
    session: bool | None = None
    storeId: str | None = None
    value: str
    expires: float | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def validate_expiration(cls, data: dict[str, Any]) -> dict[str, Any]:
        # Handle either expirationDate or expires being provided
        if data.get("expirationDate") is None and data.get("expires") is not None:
            data["expirationDate"] = float(data["expires"])
        elif data.get("expires") is None and data.get("expirationDate") is not None:
            data["expires"] = float(data["expirationDate"])
        return data

    @override
    def model_post_init(self, __context: Any) -> None:
        # Set expires if expirationDate is provided but expires is not
        if self.expirationDate is not None and self.expires is None:
            self.expires = float(self.expirationDate)
        # Set expirationDate if expires is provided but expirationDate is not
        elif self.expires is not None and self.expirationDate is None:
            self.expirationDate = float(self.expires)

        if self.sameSite is not None:
            self.sameSite = self.sameSite.lower()
            self.sameSite = self.sameSite[0].upper() + self.sameSite[1:]

    @staticmethod
    def from_json(path: str | Path) -> list["Cookie"]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Cookies file not found at {path}")
        with open(path, "r") as f:
            cookies_json = json.load(f)
        cookies = [Cookie.model_validate(cookie) for cookie in cookies_json]
        return cookies


class UploadCookiesRequest(BaseModel):
    cookies: list[Cookie]

    @staticmethod
    def from_json(path: str | Path) -> "UploadCookiesRequest":
        cookies = Cookie.from_json(path)
        return UploadCookiesRequest(cookies=cookies)


class UploadCookiesResponse(BaseModel):
    success: bool
    message: str


class SessionStartRequestDict(TypedDict, total=False):
    timeout_minutes: int
    screenshot: bool | None
    max_steps: int
    proxies: list[ProxySettings] | bool
    browser_type: BrowserType


class SessionRequestDict(TypedDict, total=False):
    session_id: Required[str]


class SessionStartRequest(BaseModel):
    timeout_minutes: Annotated[
        int,
        Field(
            description="Session timeout in minutes. Cannot exceed the global timeout.",
            gt=0,
            le=DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES,
        ),
    ] = DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES

    screenshot: Annotated[
        bool | None,
        Field(description="Whether to include a screenshot in the response."),
    ] = None

    max_steps: Annotated[
        int | None,
        Field(
            gt=0,
            description="Maximum number of steps in the trajectory. An error will be raised if this limit is reached.",
        ),
    ] = DEFAULT_MAX_NB_STEPS

    proxies: Annotated[
        list[ProxySettings] | bool,
        Field(
            description="List of custom proxies to use for the session. If True, the default proxies will be used.",
        ),
    ] = False
    browser_type: BrowserType = BrowserType.CHROMIUM

    def __post_init__(self):
        """
        Validate that the session timeout does not exceed the allowed global limit.

        Raises:
            ValueError: If the session's timeout_minutes exceeds DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES.
        """
        if self.timeout_minutes > DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES:
            raise ValueError(
                (
                    "Session timeout cannot be greater than global timeout: "
                    f"{self.timeout_minutes} > {DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES}"
                )
            )


class SessionRequest(BaseModel):
    session_id: Annotated[
        str | None,
        Field(description="The ID of the session. A new session is created when not provided."),
    ] = None


class SessionStatusRequest(BaseModel):
    session_id: Annotated[
        str | None,
        Field(description="The ID of the session. A new session is created when not provided."),
    ] = None

    replay: Annotated[
        bool,
        Field(description="Whether to include the video replay in the response (`.webp` format)."),
    ] = False


class ListRequestDict(TypedDict, total=False):
    only_active: bool
    limit: int


class SessionListRequest(BaseModel):
    only_active: bool = True
    limit: int = 10


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
        int,
        Field(description="Session timeout in minutes. Will timeout if now() > last access time + timeout_minutes"),
    ]
    created_at: Annotated[dt.datetime, Field(description="Session creation time")]
    closed_at: Annotated[dt.datetime | None, Field(description="Session closing time")] = None
    last_accessed_at: Annotated[dt.datetime, Field(description="Last access time")]
    duration: Annotated[dt.timedelta, Field(description="Session duration")]
    status: Annotated[
        Literal["active", "closed", "error", "timed_out"],
        Field(description="Session status"),
    ]
    # TODO: discuss if this is the best way to handle errors
    error: Annotated[str | None, Field(description="Error message if the operation failed to complete")] = None
    proxies: Annotated[
        bool,
        Field(
            description="Whether proxies were used for the session. True if any proxy was applied during session creation."
        ),
    ] = False
    browser_type: BrowserType = BrowserType.CHROMIUM


class SessionStatusResponse(SessionResponse):
    replay: Annotated[bytes | None, Field(description="The session replay in `.webp` format", repr=False)] = None

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }


class SessionResponseDict(TypedDict, total=False):
    session_id: str
    timeout_minutes: int
    created_at: dt.datetime
    last_accessed_at: dt.datetime
    duration: dt.timedelta
    status: Literal["active", "closed", "error", "timed_out"]
    error: str | None


# ############################################################
# Session debug endpoints
# ############################################################


class TabSessionDebugRequest(BaseModel):
    tab_idx: int


class TabSessionDebugResponse(BaseModel):
    metadata: TabsData
    debug_url: str
    ws_url: str


class SessionDebugResponse(BaseModel):
    debug_url: str
    ws_url: str
    recording_ws_url: str
    tabs: list[TabSessionDebugResponse]


class SessionDebugRecordingEvent(BaseModel):
    """Model for events that can be sent over the recording WebSocket"""

    type: Literal["action", "observation", "error"]
    data: BaseAction | Observation | str
    timestamp: dt.datetime = Field(default_factory=dt.datetime.now)

    @staticmethod
    def session_closed() -> "SessionDebugRecordingEvent":
        return SessionDebugRecordingEvent(
            type="error",
            data="Session closed by user. No more actions will be recorded.",
        )


# ############################################################
# Persona
# ############################################################


class EmailsReadRequestDict(TypedDict, total=False):
    limit: int
    timedelta: dt.timedelta | None
    unread_only: bool


class EmailsReadRequest(BaseModel):
    limit: Annotated[int, Field(description="Max number of emails to return")] = 10
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only emails that are not older than <timedelta>")
    ] = None
    unread_only: Annotated[bool, Field(description="Return only previously unread emails")] = False


class EmailResponse(BaseModel):
    subject: Annotated[str, Field(description="Subject of the email")]
    email_id: Annotated[str, Field(description="Email UUID")]
    created_at: Annotated[dt.datetime, Field(description="Creation date")]
    sender_email: Annotated[str, Field(description="Email address of the sender")]
    sender_name: Annotated[str, Field(description="Name (if available) of the sender")]
    text_content: Annotated[
        str | None, Field(description="Raw textual body, can be uncorrelated with html content")
    ] = None
    html_content: Annotated[str | None, Field(description="HTML body, can be uncorrelated with raw content")] = None


class SMSReadRequestDict(TypedDict, total=False):
    limit: int
    timedelta: dt.timedelta | None
    unread_only: bool


class SMSReadRequest(BaseModel):
    limit: Annotated[int, Field(description="Max number of messages to return")] = 10
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only messages that are not older than <timedelta>")
    ] = None
    unread_only: Annotated[bool, Field(description="Return only previously unread messages")] = False


class SMSResponse(BaseModel):
    body: Annotated[str, Field(description="SMS message body")]
    sms_id: Annotated[str, Field(description="SMS UUID")]
    created_at: Annotated[dt.datetime, Field(description="Creation date")]
    sender: Annotated[str, Field(description="SMS sender phone number")]


class PersonaCreateRequestDict(TypedDict, total=False):
    pass


class PersonaCreateRequest(BaseModel):
    pass


class PersonaCreateResponse(BaseModel):
    persona_id: Annotated[str, Field(description="ID of the created persona")]


class VirtualNumberRequestDict(TypedDict, total=False):
    pass


class VirtualNumberRequest(BaseModel):
    pass


class VirtualNumberResponse(BaseModel):
    status: Annotated[str, Field(description="Status of the created virtual number")]


# ############################################################
# Environment endpoints
# ############################################################


class PaginationParamsDict(TypedDict, total=False):
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
    url: Annotated[
        str | None,
        Field(description="The URL to observe. If not provided, uses the current page URL."),
    ] = None


class ObserveRequestDict(SessionRequestDict, PaginationParamsDict, total=False):
    url: str | None


class ScrapeParamsDict(TypedDict, total=False):
    scrape_images: bool
    scrape_links: bool
    only_main_content: bool
    response_format: type[BaseModel] | None
    instructions: str | None
    use_llm: bool | None


class ScrapeRequestDict(ObserveRequestDict, ScrapeParamsDict, total=False):
    pass


class ScrapeParams(BaseModel):
    scrape_images: Annotated[
        bool,
        Field(description="Whether to scrape images from the page. Images are not scraped by default."),
    ] = False

    scrape_links: Annotated[
        bool,
        Field(description="Whether to scrape links from the page. Links are scraped by default."),
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
        type[BaseModel] | None,
        Field(description="The response format to use for the scrape."),
    ] = None
    instructions: Annotated[str | None, Field(description="The instructions to use for the scrape.")] = None

    use_llm: Annotated[
        bool | None,
        Field(
            description=(
                "Whether to use an LLM for the extraction process. This will result in a longer response time but a"
                " better accuracy. If not provided, the default value is the same as the NotteEnv config."
            )
        ),
    ] = None

    def requires_schema(self) -> bool:
        return self.response_format is not None or self.instructions is not None

    def scrape_params_dict(self) -> ScrapeParamsDict:
        return ScrapeParamsDict(
            scrape_images=self.scrape_images,
            scrape_links=self.scrape_links,
            only_main_content=self.only_main_content,
            response_format=self.response_format,
            instructions=self.instructions,
            use_llm=self.use_llm,
        )

    @field_validator("response_format", mode="before")
    @classmethod
    def convert_response_format(cls, value: dict[str, Any] | type[BaseModel] | None) -> type[BaseModel] | None:
        """
        Creates a Pydantic model from a given JSON Schema.

        Args:
            schema_name: The name of the model to be created.
            schema_json: The JSON Schema definition.

        Returns:
            The dynamically created Pydantic model class.
        """
        if value is None:
            return None
        if isinstance(value, type) and issubclass(value, BaseModel):  # type: ignore[arg-type]
            return value
        if not isinstance(value, dict):  # type: ignore[arg-type]
            raise ValueError(f"response_format must be a BaseModel or a dict but got: {type(value)} : {value}")  # type: ignore[unreachable]
        if len(value.keys()) == 0:
            return None

        # Map JSON Schema types to Pydantic types
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": None,
        }
        if "properties" not in value:
            raise ValueError("response_format must contain a 'properties' key")

        if "$defs" in value:
            raise ValueError("response_format currently does not support $defs")

        # Extract field definitions with type annotations
        field_definitions = {}
        for field_name, field_schema in value["properties"].items():
            field_type = field_schema.get("type")
            if field_type:
                python_type = type_mapping.get(field_type)
                if python_type:
                    field_definitions[field_name] = (python_type, ...)

        model_name = str(value.get("title", "__DynamicResponseFormat"))

        return create_model(model_name, **field_definitions)  # type: ignore[arg-type]


class ScrapeRequest(ObserveRequest, ScrapeParams):
    pass


class StepRequest(SessionRequest, PaginationParams):
    action_id: Annotated[str, Field(description="The ID of the action to execute")]

    value: Annotated[str | None, Field(description="The value to input for form actions")] = None

    enter: Annotated[
        bool | None,
        Field(description="Whether to press enter after inputting the value"),
    ] = None


class StepRequestDict(SessionRequestDict, PaginationParamsDict, total=False):
    action_id: str
    value: str | None
    enter: bool | None


class ActionSpaceResponse(BaseModel):
    markdown: Annotated[str | None, Field(description="Markdown representation of the action space")] = None
    actions: Annotated[
        Sequence[Action],
        Field(description="List of available actions in the current state"),
    ]
    browser_actions: Annotated[
        Sequence[BrowserAction],
        Field(description="List of special actions, i.e browser actions"),
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
            actions=space.actions(),  # type: ignore[arg-type]
            browser_actions=space.browser_actions(),  # type: ignore[arg-type]
        )


class ObserveResponse(BaseModel):
    session: Annotated[SessionResponse, Field(description="Browser session information")]
    space: Annotated[
        ActionSpaceResponse | None,
        Field(description="Available actions in the current state"),
    ] = None
    metadata: SnapshotMetadata
    screenshot: bytes | None = Field(repr=False)
    data: DataSpace | None
    progress: TrajectoryProgress | None

    model_config = {  # type: ignore[attr-defined]
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
            data=obs.data,
            space=ActionSpaceResponse.from_space(obs.space),
            progress=obs.progress,
        )


# ############################################################
# Agent endpoints
# ############################################################


class AgentRequestDict(TypedDict, total=False):
    task: Required[str]
    url: str | None
    reasoning_model: LlmModel


class AgentRequest(BaseModel):
    task: str
    url: str | None = None


class AgentStatus(StrEnum):
    active = "active"
    closed = "closed"


class AgentSessionRequest(SessionRequest):
    agent_id: Annotated[str | None, Field(description="The ID of the agent to run")] = None


class AgentRunRequestDict(AgentRequestDict, SessionRequestDict, total=False):
    pass


class AgentRunRequest(AgentRequest, SessionRequest):
    reasoning_model: LlmModel = LlmModel.default()  # type: ignore[reportCallInDefaultInitializer]
    use_vision: bool = True


class AgentStatusRequest(AgentSessionRequest):
    @field_validator("agent_id", mode="before")
    @classmethod
    def validate_agent_id(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("agent_id is required")
        return value


class AgentListRequest(SessionListRequest):
    pass


class AgentStopRequest(AgentSessionRequest):
    success: Annotated[bool, Field(description="Whether the agent task was successful")] = False
    answer: Annotated[str, Field(description="The answer to the agent task")] = "Agent manually stopped by user"
    replay: Annotated[bytes | None, Field(description="The session replay in `.webp` format", repr=False)] = None

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }


class AgentResponse(BaseModel):
    agent_id: Annotated[str, Field(description="The ID of the agent")]
    created_at: Annotated[dt.datetime, Field(description="The creation time of the agent")]
    session_id: Annotated[str, Field(description="The ID of the session")]
    status: Annotated[AgentStatus, Field(description="The status of the agent (active or closed)")]
    closed_at: Annotated[dt.datetime | None, Field(description="The closing time of the agent")] = None


TStepOutput = TypeVar("TStepOutput", bound=BaseModel)


class AgentStatusResponse(AgentResponse, Generic[TStepOutput]):
    task: Annotated[str, Field(description="The task that the agent is currently running")]
    url: Annotated[str | None, Field(description="The URL that the agent started on")] = None

    success: Annotated[
        bool | None,
        Field(description="Whether the agent task was successful. None if the agent is still running"),
    ] = None
    answer: Annotated[
        str | None,
        Field(description="The answer to the agent task. None if the agent is still running"),
    ] = None
    steps: Annotated[
        list[TStepOutput],
        Field(description="The steps that the agent has currently taken"),
    ] = Field(default_factory=lambda: [])
    replay: Annotated[bytes | None, Field(description="The session replay in `.webp` format", repr=False)] = None

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @field_validator("replay", mode="before")
    @classmethod
    def decode_replay(cls, value: str | None) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if not isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("replay must be a bytes or a base64 encoded string")  # pyright: ignore[reportUnreachable]
        return b64decode(value.encode("utf-8"))
