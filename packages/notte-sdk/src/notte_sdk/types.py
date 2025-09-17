import datetime as dt
import json
import os
import re
from base64 import b64decode, b64encode
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Required

from notte_core.actions import (
    ActionUnion,
    ActionValidation,
    BaseAction,
    BrowserAction,
    InteractionAction,
)
from notte_core.agent_types import AgentCompletion
from notte_core.browser.dom_tree import NodeSelectors
from notte_core.browser.observation import ExecutionResult, Observation
from notte_core.browser.snapshot import TabsData
from notte_core.common.config import (
    BrowserType,
    LlmModel,
    PerceptionType,
    PlaywrightProxySettings,
    ScreenshotType,
    config,
)
from notte_core.credentials.base import Credential, CredentialsDict, CreditCardDict
from notte_core.data.space import DataSpace
from notte_core.trajectory import ElementLiteral
from notte_core.utils.pydantic_schema import convert_response_format_to_pydantic_model
from notte_core.utils.url import get_root_domain
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pyotp import TOTP
from typing_extensions import NotRequired, TypedDict, override

# ############################################################
# Session Management
# ############################################################


DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES = 3
DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES = 30
DEFAULT_MAX_NB_ACTIONS = 100
DEFAULT_LIMIT_LIST_ITEMS = 10
DEFAULT_MAX_NB_STEPS = config.max_steps

DEFAULT_HEADLESS_VIEWPORT_WIDTH = 1280
DEFAULT_HEADLESS_VIEWPORT_HEIGHT = 1080

DEFAULT_VIEWPORT_WIDTH = config.viewport_width
DEFAULT_VIEWPORT_HEIGHT = config.viewport_height
DEFAULT_BROWSER_TYPE = config.browser_type
DEFAULT_USER_AGENT = config.user_agent
DEFAULT_CHROME_ARGS = config.chrome_args


class SdkRequest(BaseModel):
    # forbid extra fields in request
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SdkResponse(BaseModel):
    # allow extra fields in response
    pass


class ExecutionResponse(SdkResponse):
    """Used for page operation like setting cookies"""

    success: Annotated[bool, Field(description="Whether the operation was successful")]
    message: Annotated[str, Field(description="A message describing the operation")]


class ProxyGeolocationCountry(StrEnum):
    ANDORRA = "ad"
    UNITED_ARAB_EMIRATES = "ae"
    AFGHANISTAN = "af"
    ANTIGUA_AND_BARBUDA = "ag"
    ANGUILLA = "ai"
    ALBANIA = "al"
    ARMENIA = "am"
    ANGOLA = "ao"
    ARGENTINA = "ar"
    AUSTRIA = "at"
    AUSTRALIA = "au"
    ARUBA = "aw"
    AZERBAIJAN = "az"
    BOSNIA_AND_HERZEGOVINA = "ba"
    BARBADOS = "bb"
    BANGLADESH = "bd"
    BELGIUM = "be"
    BURKINA_FASO = "bf"
    BULGARIA = "bg"
    BAHRAIN = "bh"
    BURUNDI = "bi"
    BENIN = "bj"
    BERMUDA = "bm"
    BRUNEI = "bn"
    BOLIVIA = "bo"
    CARIBBEAN_NETHERLANDS = "bq"
    BRAZIL = "br"
    BAHAMAS = "bs"
    BHUTAN = "bt"
    BOTSWANA = "bw"
    BELARUS = "by"
    BELIZE = "bz"
    CANADA = "ca"
    DEMOCRATIC_REPUBLIC_OF_THE_CONGO = "cd"
    REPUBLIC_OF_THE_CONGO = "cg"
    SWITZERLAND = "ch"
    COTE_D_IVOIRE = "ci"
    CHILE = "cl"
    CAMEROON = "cm"
    CHINA = "cn"
    COLOMBIA = "co"
    COSTA_RICA = "cr"
    CUBA = "cu"
    CAPE_VERDE = "cv"
    CURACAO = "cw"
    CYPRUS = "cy"
    CZECH_REPUBLIC = "cz"
    GERMANY = "de"
    DJIBOUTI = "dj"
    DENMARK = "dk"
    DOMINICA = "dm"
    DOMINICAN_REPUBLIC = "do"
    ALGERIA = "dz"
    ECUADOR = "ec"
    ESTONIA = "ee"
    EGYPT = "eg"
    SPAIN = "es"
    ETHIOPIA = "et"
    FINLAND = "fi"
    FIJI = "fj"
    FRANCE = "fr"
    GABON = "ga"
    UNITED_KINGDOM = "gb"
    GRENADA = "gd"
    GEORGIA = "ge"
    FRENCH_GUIANA = "gf"
    GUERNSEY = "gg"
    GHANA = "gh"
    GIBRALTAR = "gi"
    GAMBIA = "gm"
    GUINEA = "gn"
    GUADELOUPE = "gp"
    EQUATORIAL_GUINEA = "gq"
    GREECE = "gr"
    GUATEMALA = "gt"
    GUAM = "gu"
    GUINEA_BISSAU = "gw"
    GUYANA = "gy"
    HONG_KONG = "hk"
    HONDURAS = "hn"
    CROATIA = "hr"
    HAITI = "ht"
    HUNGARY = "hu"
    INDONESIA = "id"
    IRELAND = "ie"
    ISRAEL = "il"
    ISLE_OF_MAN = "im"
    INDIA = "in"
    IRAQ = "iq"
    IRAN = "ir"
    ICELAND = "is"
    ITALY = "it"
    JERSEY = "je"
    JAMAICA = "jm"
    JORDAN = "jo"
    JAPAN = "jp"
    KENYA = "ke"
    KYRGYZSTAN = "kg"
    CAMBODIA = "kh"
    SAINT_KITTS_AND_NEVIS = "kn"
    SOUTH_KOREA = "kr"
    KUWAIT = "kw"
    CAYMAN_ISLANDS = "ky"
    KAZAKHSTAN = "kz"
    LAOS = "la"
    LEBANON = "lb"
    SAINT_LUCIA = "lc"
    SRI_LANKA = "lk"
    LIBERIA = "lr"
    LESOTHO = "ls"
    LITHUANIA = "lt"
    LUXEMBOURG = "lu"
    LATVIA = "lv"
    LIBYA = "ly"
    MOROCCO = "ma"
    MOLDOVA = "md"
    MONTENEGRO = "me"
    SAINT_MARTIN = "mf"
    MADAGASCAR = "mg"
    NORTH_MACEDONIA = "mk"
    MALI = "ml"
    MYANMAR = "mm"
    MONGOLIA = "mn"
    MACAO = "mo"
    MARTINIQUE = "mq"
    MAURITANIA = "mr"
    MALTA = "mt"
    MAURITIUS = "mu"
    MALDIVES = "mv"
    MALAWI = "mw"
    MEXICO = "mx"
    MALAYSIA = "my"
    MOZAMBIQUE = "mz"
    NAMIBIA = "na"
    NEW_CALEDONIA = "nc"
    NIGER = "ne"
    NIGERIA = "ng"
    NICARAGUA = "ni"
    NETHERLANDS = "nl"
    NORWAY = "no"
    NEPAL = "np"
    NEW_ZEALAND = "nz"
    OMAN = "om"
    PANAMA = "pa"
    PERU = "pe"
    FRENCH_POLYNESIA = "pf"
    PAPUA_NEW_GUINEA = "pg"
    PHILIPPINES = "ph"
    PAKISTAN = "pk"
    POLAND = "pl"
    PUERTO_RICO = "pr"
    STATE_OF_PALESTINE = "ps"
    PORTUGAL = "pt"
    PARAGUAY = "py"
    QATAR = "qa"
    REUNION = "re"
    ROMANIA = "ro"
    SERBIA = "rs"
    RUSSIA = "ru"
    RWANDA = "rw"
    SAUDI_ARABIA = "sa"
    SEYCHELLES = "sc"
    SUDAN = "sd"
    SWEDEN = "se"
    SINGAPORE = "sg"
    SLOVENIA = "si"
    SLOVAKIA = "sk"
    SIERRA_LEONE = "sl"
    SAN_MARINO = "sm"
    SENEGAL = "sn"
    SOMALIA = "so"
    SURINAME = "sr"
    SOUTH_SUDAN = "ss"
    SAO_TOME_AND_PRINCIPE = "st"
    EL_SALVADOR = "sv"
    SINT_MAARTEN = "sx"
    SYRIA = "sy"
    SWAZILAND = "sz"
    TURKS_AND_CAICOS_ISLANDS = "tc"
    TOGO = "tg"
    THAILAND = "th"
    TAJIKISTAN = "tj"
    TURKMENISTAN = "tm"
    TUNISIA = "tn"
    TURKEY = "tr"
    TRINIDAD_AND_TOBAGO = "tt"
    TAIWAN_PROVINCE = "tw"
    TANZANIA = "tz"
    UKRAINE = "ua"
    UGANDA = "ug"
    UNITED_STATES = "us"
    URUGUAY = "uy"
    UZBEKISTAN = "uz"
    SAINT_VINCENT_AND_THE_GRENADINES = "vc"
    VENEZUELA = "ve"
    BRITISH_VIRGIN_ISLANDS = "vg"
    UNITED_STATES_VIRGIN_ISLANDS = "vi"
    VIETNAM = "vn"
    YEMEN = "ye"
    SOUTH_AFRICA = "za"
    ZAMBIA = "zm"
    ZIMBABWE = "zw"


class ProxyGeolocation(SdkRequest):
    """
    Geolocation settings for the proxy.
    E.g. "New York, NY, US"
    """

    country: ProxyGeolocationCountry
    # TODO: enable city & state later on
    # city: str
    # state: str


class NotteProxy(SdkRequest):
    type: Literal["notte"] = "notte"
    geolocation: ProxyGeolocation | None = None
    # TODO: enable domainPattern later on
    # domainPattern: str | None = None

    @staticmethod
    def from_country(country: str) -> "NotteProxy":
        return NotteProxy(geolocation=ProxyGeolocation(country=ProxyGeolocationCountry(country)))


class ExternalProxy(SdkRequest):
    type: Literal["external"] = "external"
    server: str
    username: str | None = None
    password: str | None = None
    bypass: str | None = None

    @staticmethod
    def from_env() -> "ExternalProxy":
        server = os.getenv("PROXY_URL")
        username = os.getenv("PROXY_USERNAME")
        password = os.getenv("PROXY_PASSWORD")
        bypass = os.getenv("PROXY_BYPASS")
        if server is None:
            raise ValueError("PROXY_URL must be set")
        return ExternalProxy(
            server=server,
            username=username,
            password=password,
            bypass=bypass,
        )


ProxySettings = Annotated[NotteProxy | ExternalProxy, Field(discriminator="type")]


class Cookie(SdkRequest):
    name: str
    value: str
    domain: str
    path: str
    httpOnly: bool
    expirationDate: float | None = None
    hostOnly: bool | None = None
    sameSite: Literal["Lax", "None", "Strict"] | None = None
    secure: bool | None = None
    session: bool | None = None
    storeId: str | None = None
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
            self.sameSite = self.sameSite.lower()  # type: ignore
            self.sameSite = self.sameSite[0].upper() + self.sameSite[1:]  # type: ignore

    @staticmethod
    def from_json(path: str | Path) -> list["Cookie"]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Cookies file not found at {path}")
        with open(path, "r") as f:
            cookies_json = json.load(f)
        cookies = [Cookie.model_validate(cookie) for cookie in cookies_json]
        return cookies

    @staticmethod
    def dump_json(cookies: list["Cookie"], path: str | Path) -> int:
        path = Path(path)
        cookies_dump = [cookie.model_dump() for cookie in cookies]
        return path.write_text(json.dumps(cookies_dump))


class SetCookiesRequest(SdkRequest):
    cookies: list[Cookie]

    @staticmethod
    def from_json(path: str | Path) -> "SetCookiesRequest":
        cookies = Cookie.from_json(path)
        return SetCookiesRequest(cookies=cookies)


class SetCookiesResponse(SdkResponse):
    success: bool
    message: str


class GetCookiesResponse(SdkResponse):
    cookies: list[Cookie]


class SessionOffsetResponse(SdkResponse):
    offset: Annotated[int, Field(description="Current state of the session trajectory")]


class ReplayResponse(SdkResponse):
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

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        if self.replay is not None:
            data["replay"] = b64encode(self.replay).decode("utf-8")
        return data


class SessionStartRequestDict(TypedDict, total=False):
    """Request dictionary for starting a session.

    Args:
        headless: Whether to run the session in headless mode.
        solve_captchas: Whether to try to automatically solve captchas
        timeout_minutes: Session timeout in minutes. Cannot exceed the global timeout.
        proxies: List of custom proxies to use for the session. If True, the default proxies will be used.
        browser_type: The browser type to use. Can be chromium, chrome or firefox.
        user_agent: The user agent to use for the session
        chrome_args: Overwrite the chrome instance arguments
        viewport_width: The width of the viewport
        viewport_height: The height of the viewport
        cdp_url: The CDP URL of another remote session provider.
        use_file_storage: Whether FileStorage should be attached to the session.
        screenshot_type: The type of screenshot to use for the session.
    """

    headless: bool
    solve_captchas: bool
    timeout_minutes: int
    proxies: list[ProxySettings] | bool
    browser_type: BrowserType
    user_agent: str | None
    chrome_args: list[str] | None
    viewport_width: int | None
    viewport_height: int | None
    cdp_url: str | None
    use_file_storage: bool
    screenshot_type: ScreenshotType


class SessionStartRequest(SdkRequest):
    headless: Annotated[bool, Field(description="Whether to run the session in headless mode.")] = config.headless
    solve_captchas: Annotated[bool, Field(description="Whether to try to automatically solve captchas")] = (
        config.solve_captchas
    )

    timeout_minutes: Annotated[
        int,
        Field(
            description="Session timeout in minutes. Cannot exceed the global timeout.",
            gt=0,
            le=DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES,
        ),
    ] = DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES

    proxies: Annotated[
        list[ProxySettings] | bool,
        Field(
            description="List of custom proxies to use for the session. If True, the default proxies will be used.",
        ),
    ] = False
    browser_type: Annotated[
        BrowserType, Field(description="The browser type to use. Can be chromium, chrome or firefox.")
    ] = DEFAULT_BROWSER_TYPE
    user_agent: Annotated[str | None, Field(description="The user agent to use for the session")] = DEFAULT_USER_AGENT
    chrome_args: Annotated[list[str] | None, Field(description="Overwrite the chrome instance arguments")] = Field(
        default_factory=lambda: DEFAULT_CHROME_ARGS
    )
    viewport_width: Annotated[int | None, Field(description="The width of the viewport")] = DEFAULT_VIEWPORT_WIDTH
    viewport_height: Annotated[int | None, Field(description="The height of the viewport")] = DEFAULT_VIEWPORT_HEIGHT

    cdp_url: Annotated[str | None, Field(description="The CDP URL of another remote session provider.")] = (
        config.cdp_url
    )

    use_file_storage: Annotated[bool, Field(description="Whether FileStorage should be attached to the session.")] = (
        False
    )

    screenshot_type: Annotated[ScreenshotType, Field(description="The type of screenshot to use for the session.")] = (
        config.screenshot_type
    )

    @field_validator("timeout_minutes")
    @classmethod
    def validate_timeout_minutes(cls, value: int) -> int:
        """
        Validate that the session timeout does not exceed the allowed global limit.

        Raises:
            ValueError: If the session's timeout_minutes exceeds DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES.
        """
        if value > DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES:
            raise ValueError(
                (
                    "Session timeout cannot be greater than global timeout: "
                    f"{value} > {DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES}"
                )
            )
        return value

    @model_validator(mode="after")
    def check_viewport(self) -> "SessionStartRequest":
        if (self.viewport_width is None) != (self.viewport_height is None):
            raise ValueError("Both viewport_width and viewport_height must be set together or both must be None")
        return self

    @model_validator(mode="after")
    def validate_cdp_url_constraints(self) -> "SessionStartRequest":
        """
        Validate that when cdp_url is provided, certain fields are set to their default values.

        Raises:
            ValueError: If cdp_url is provided but other fields are not set to defaults.
        """
        if self.cdp_url is not None:
            if self.solve_captchas:
                raise ValueError(
                    "When cdp_url is provided, solve_captchas must be set to False. Set the solve_captchas with your external session CDP provider."
                )
            if self.proxies is not False:
                raise ValueError(
                    "When cdp_url is provided, proxies must be set to False. Set the proxies with your external session CDP provider."
                )
            if self.user_agent is not None:
                raise ValueError(
                    "When cdp_url is provided, user_agent must be None. Set the user agent with your external session CDP provider."
                )
            if self.chrome_args is not None:
                raise ValueError(
                    "When cdp_url is provided, chrome_args must be None. Set the chrome arguments with your external session CDP provider."
                )
            if self.viewport_width is not None and self.viewport_width != DEFAULT_VIEWPORT_WIDTH:
                raise ValueError(
                    "When cdp_url is provided, viewport_width must be None. Set the viewport width with your external session CDP provider."
                )
            if self.viewport_height is not None and self.viewport_height != DEFAULT_VIEWPORT_HEIGHT:
                raise ValueError(
                    "When cdp_url is provided, viewport_height must be None. Set the viewport height with your external session CDP provider."
                )
        return self

    @property
    def playwright_proxy(self) -> PlaywrightProxySettings | None:
        if self.proxies is True:
            if config.playwright_proxy is not None:
                return config.playwright_proxy
            # proxy=true => use notte proxy
            base_proxy = NotteProxy()
        elif self.proxies is False or len(self.proxies) == 0:
            return None
        elif len(self.proxies) > 1:
            raise ValueError(f"Multiple proxies are not supported yet. Got {len(self.proxies)} proxies.")
        else:
            base_proxy = self.proxies[0]

        match base_proxy.type:
            case "notte":
                raise NotImplementedError(
                    "Notte proxy only supported in cloud browser sessions. Please use our API to create a session with a proxy or provide an external proxy."
                )
            case "external":
                return PlaywrightProxySettings(
                    server=base_proxy.server,
                    bypass=base_proxy.bypass,
                    username=base_proxy.username,
                    password=base_proxy.password,
                )
        raise ValueError(f"Unsupported proxy type: {base_proxy.type}")  # pyright: ignore[reportUnreachable]


class SessionStatusRequest(SdkRequest):
    session_id: Annotated[
        str | None,
        Field(description="The ID of the session. A new session is created when not provided."),
    ] = None

    replay: Annotated[
        bool,
        Field(description="Whether to include the video replay in the response (`.webp` format)."),
    ] = False


class SessionListRequestDict(TypedDict, total=False):
    only_active: bool
    page_size: int
    page: int


class SessionListRequest(SdkRequest):
    only_active: bool = True
    page_size: int = DEFAULT_LIMIT_LIST_ITEMS
    page: int = 1


class SessionResponse(SdkResponse):
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
    duration: Annotated[dt.timedelta, Field(description="Session duration")] = Field(
        default_factory=lambda: dt.timedelta(0)
    )
    status: Annotated[
        Literal["active", "closed", "error", "timed_out"],
        Field(description="Session status"),
    ]
    steps: Annotated[list[dict[str, Any]], Field(description="Steps of the session", repr=False)] = Field(
        default_factory=lambda: []
    )

    # TODO: discuss if this is the best way to handle errors
    error: Annotated[str | None, Field(description="Error message if the operation failed to complete")] = None
    credit_usage: Annotated[float | None, Field(description="Credit usage for the session. None")] = None
    proxies: Annotated[
        bool,
        Field(
            description="Whether proxies were used for the session. True if any proxy was applied during session creation."
        ),
    ] = False
    browser_type: BrowserType = "chromium"
    use_file_storage: Annotated[bool, Field(description="Whether FileStorage was attached to the session.")] = False

    @field_validator("closed_at", mode="before")
    @classmethod
    def validate_closed_at(cls, value: dt.datetime | None, info: Any) -> dt.datetime | None:
        data = info.data
        if data.get("status") == "closed" and value is None:
            raise ValueError("closed_at must be provided if status is closed")
        return value

    @field_validator("duration", mode="before")
    @classmethod
    def compute_duration(cls, value: dt.timedelta | None, info: Any) -> dt.timedelta:
        data = info.data
        if value is not None:
            return value
        if data.get("status") == "closed" and data.get("closed_at") is not None:
            return data["closed_at"] - data["created_at"]
        return dt.datetime.now() - data["created_at"]


class SessionStatusResponse(SessionResponse, ReplayResponse):
    pass


class ListFilesResponse(SdkResponse):
    files: Annotated[list[str], Field(description="Names of available files")]


class FileUploadResponse(SdkResponse):
    success: Annotated[bool, Field(description="Whether the upload was successful")]


class FileLinkResponse(SdkResponse):
    url: Annotated[str, Field(description="URL to download file from")]


class DownloadFileRequest(SdkRequest):
    filename: Annotated[str, Field(description="Name of file to download")]


class DownloadsListRequest(SdkRequest):
    session_id: Annotated[str, Field(description="Session ID")]


# ############################################################
# Session debug endpoints
# ############################################################


class TabSessionDebugRequest(SdkRequest):
    tab_idx: int


class TabSessionDebugResponse(SdkResponse):
    metadata: TabsData
    debug_url: str
    ws_url: str


class WebSocketUrls(SdkRequest):
    cdp: Annotated[str, Field(description="WebSocket URL to connect using CDP protocol")]
    recording: Annotated[str, Field(description="WebSocket URL for live session recording (screenshot stream)")]
    logs: Annotated[str, Field(description="WebSocket URL for live logs (obsveration / actions events)")]


class SessionDebugResponse(SdkResponse):
    debug_url: str
    ws: WebSocketUrls
    tabs: list[TabSessionDebugResponse]


class SessionDebugRecordingEvent(SdkResponse):
    """Model for events that can be sent over the recording WebSocket"""

    type: ElementLiteral | Literal["error"]
    data: AgentCompletion | Observation | ExecutionResult | str
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())

    @staticmethod
    def session_closed() -> "SessionDebugRecordingEvent":
        return SessionDebugRecordingEvent(
            type="error",
            data="Session closed by user. No more actions will be recorded.",
        )


# ############################################################
# Vaults
# ############################################################


class VaultCreateRequestDict(TypedDict, total=False):
    """Request dictionary for creating a new vault."""

    name: str


class VaultCreateRequest(SdkRequest):
    name: Annotated[str, Field(description="Name of the vault")] = "default"


class ListCredentialsRequestDict(TypedDict, total=False):
    """Request dictionary for listing credentials."""

    pass


class ListCredentialsRequest(SdkRequest):
    pass


class ListCredentialsResponse(SdkResponse):
    credentials: Annotated[list[Credential], Field(description="URLs for which we hold credentials")]


class VaultListRequestDict(SessionListRequestDict, total=False):
    """Request dictionary for listing vaults."""

    pass


class VaultListRequest(SessionListRequest):
    pass


class AddCredentialsRequestDict(CredentialsDict, total=True):
    """Request dictionary for adding credentials.

    Args:
        url: The URL to add credentials for
    """

    url: str


def validate_url(value: str | None) -> str | None:
    if value is None:
        return None
    domain_url = get_root_domain(value)
    if len(domain_url) == 0:
        raise ValueError(f"Invalid URL: {value}. Please provide a valid URL with a domain name.")
    return domain_url


class AddCredentialsRequest(SdkRequest):
    url: str
    credentials: Annotated[CredentialsDict, Field(description="Credentials to add")]

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return validate_url(value)

    @field_validator("credentials", mode="after")
    @classmethod
    def check_email_and_username(cls, value: CredentialsDict) -> CredentialsDict:
        username = value.get("username")
        email = value.get("email")

        if username is not None and email is not None:
            raise ValueError("Can only set either username or email")

        if username is None and email is None:
            raise ValueError("Need to have either username or email set")

        secret = value.get("mfa_secret")
        if secret is not None:
            try:
                _ = TOTP(secret).now()
            except Exception:
                raise ValueError("Invalid MFA secret code: did you try to store an OTP instead of a secret?")

        return value

    @classmethod
    def from_dict(cls, dic: AddCredentialsRequestDict) -> "AddCredentialsRequest":
        return AddCredentialsRequest(
            url=dic["url"],
            credentials={key: value for key, value in dic.items() if key != "url"},  # pyright: ignore[reportArgumentType]
        )


class AddCredentialsResponse(SdkResponse):
    status: Annotated[str, Field(description="Status of the created credentials")]


class GetCredentialsRequestDict(TypedDict, total=False):
    """Request dictionary for getting credentials.

    Args:
        url: The URL to get credentials for
    """

    url: str


class GetCredentialsRequest(SdkRequest):
    url: str

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return validate_url(value)


class GetCredentialsResponse(SdkResponse):
    credentials: Annotated[CredentialsDict, Field(description="Retrieved credentials")]

    @field_validator("credentials", mode="after")
    @classmethod
    def check_email_and_username(cls, value: CredentialsDict) -> CredentialsDict:
        username = value.get("username")
        email = value.get("email")

        if username is not None and email is not None:
            raise ValueError("Can only set either username or email")

        if username is None and email is None:
            raise ValueError("Need to have either username or email set")

        return value


class DeleteCredentialsRequestDict(TypedDict, total=False):
    """Request dictionary for deleting credentials.

    Args:
        url: The URL to delete credentials for
    """

    url: str


class DeleteCredentialsRequest(SdkRequest):
    url: str

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return validate_url(value)


class DeleteCredentialsResponse(SdkResponse):
    status: Annotated[Literal["success", "failure"], Field(description="Status of the deletion")]
    message: Annotated[str, Field(description="Message of the deletion")] = "Credentials deleted successfully"


class DeleteVaultRequestDict(TypedDict, total=False):
    """Request dictionary for deleting a vault."""

    pass


class DeleteVaultRequest(SdkRequest):
    pass


class DeleteVaultResponse(SdkResponse):
    status: Annotated[Literal["success", "failure"], Field(description="Status of the deletion")]
    message: Annotated[str, Field(description="Message of the deletion")] = "Vault deleted successfully"


class AddCreditCardRequestDict(CreditCardDict, total=True):
    """Request dictionary for adding a credit card."""

    pass


class AddCreditCardRequest(SdkRequest):
    credit_card: Annotated[CreditCardDict, Field(description="Credit card to add")]

    @classmethod
    def from_dict(cls, dic: AddCreditCardRequestDict) -> "AddCreditCardRequest":
        return AddCreditCardRequest(credit_card=dic)


class AddCreditCardResponse(SdkResponse):
    status: Annotated[str, Field(description="Status of the created credit card")]


class GetCreditCardRequestDict(TypedDict, total=False):
    """Request dictionary for getting a credit card."""

    pass


class GetCreditCardRequest(SdkRequest):
    pass


class GetCreditCardResponse(SdkResponse):
    credit_card: Annotated[CreditCardDict, Field(description="Retrieved credit card")]


class DeleteCreditCardRequestDict(TypedDict, total=False):
    """Request dictionary for deleting a credit card."""

    pass


class DeleteCreditCardRequest(SdkRequest):
    pass


class DeleteCreditCardResponse(SdkResponse):
    status: Annotated[Literal["success", "failure"], Field(description="Status of the deletion")]
    message: Annotated[str, Field(description="Message of the deletion")] = "Credit card deleted successfully"


# ############################################################
# Persona
# ############################################################


class PersonaCreateRequestDict(TypedDict, total=False):
    """Request dictionary for creating a new persona."""

    create_vault: bool
    create_phone_number: bool


class PersonaCreateRequest(SdkRequest):
    create_vault: Annotated[bool, Field(description="Whether to create a vault for the persona")] = False
    create_phone_number: Annotated[bool, Field(description="Whether to create a phone number for the persona")] = False


class PersonaResponse(SdkResponse):
    persona_id: Annotated[str, Field(description="ID of the created persona")]
    status: Annotated[str, Field(description="Status of the persona (active, closed)")]
    first_name: Annotated[str, Field(description="First name of the persona")]
    last_name: Annotated[str, Field(description="Last name of the persona")]
    email: Annotated[str, Field(description="Email of the persona")]
    vault_id: Annotated[str | None, Field(description="ID of the vault")]
    phone_number: Annotated[str | None, Field(description="Phone number of the persona (optional)")]


class DeletePersonaResponse(SdkResponse):
    status: Annotated[Literal["success", "failure"], Field(description="Status of the deletion")]
    message: Annotated[str, Field(description="Message of the deletion")] = "Persona deleted successfully"


class MessageReadRequestDict(TypedDict, total=False):
    """Request dictionary for reading emails.

    Args:
        limit: Max number of emails to return
        timedelta: Return only emails that are not older than `timedelta`
        unread_only: Return only previously unread emails
    """

    limit: int
    timedelta: dt.timedelta | None
    only_unread: bool


class MessageReadRequest(SdkRequest):
    limit: Annotated[int, Field(description="Max number of emails to return")] = DEFAULT_LIMIT_LIST_ITEMS
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only emails that are not older than `timedelta`")
    ] = None
    only_unread: Annotated[bool, Field(description="Return only previously unread emails")] = False


class EmailResponse(SdkResponse):
    subject: Annotated[str, Field(description="Subject of the email")]
    email_id: Annotated[str, Field(description="Email UUID")]
    created_at: Annotated[dt.datetime, Field(description="Creation date")]
    sender_email: Annotated[str | None, Field(description="Email address of the sender")]
    sender_name: Annotated[str | None, Field(description="Name (if available) of the sender")]
    text_content: Annotated[
        str | None, Field(description="Raw textual body, can be uncorrelated with html content")
    ] = None
    html_content: Annotated[str | None, Field(description="HTML body, can be uncorrelated with raw content")] = None

    def links(self) -> list[str]:
        if self.text_content is None:
            return []
        # Match all URLs in the text, including those in markdown links and plain text
        url_pattern = r"https?://[^\s\]\)]+"
        return re.findall(url_pattern, self.text_content)


class SMSResponse(SdkResponse):
    body: Annotated[str, Field(description="SMS message body")]
    sms_id: Annotated[str, Field(description="SMS UUID")]
    created_at: Annotated[dt.datetime, Field(description="Creation date")]
    sender: Annotated[str | None, Field(description="SMS sender phone number")]


class CreatePhoneNumberRequestDict(TypedDict, total=False):
    """Request dictionary for virtual number operations."""

    pass


class CreatePhoneNumberRequest(SdkRequest):
    pass


class CreatePhoneNumberResponse(SdkResponse):
    phone_number: Annotated[str, Field(description="The phone number that was created")]
    status: Annotated[str, Field(description="Status of the created virtual number")]


class DeletePhoneNumberResponse(SdkResponse):
    status: Annotated[Literal["success", "failure"], Field(description="Status of the deletion")]
    message: Annotated[str, Field(description="Message of the deletion")] = "Phone number deleted successfully"


class PersonaListRequestDict(SessionListRequestDict, total=False):
    """Request dictionary for listing personas."""

    pass


class PersonaListRequest(SessionListRequest):
    pass


# ############################################################
# Environment endpoints
# ############################################################


class PaginationParamsDict(TypedDict, total=False):
    """Request dictionary for pagination parameters.

    Args:
        min_nb_actions: The minimum number of actions to list before stopping. If not provided, the listing will continue until the maximum number of actions is reached.
        max_nb_actions: The maximum number of actions to list after which the listing will stop. Used when min_nb_actions is not provided.
    """

    min_nb_actions: int | None
    max_nb_actions: int


class PaginationParams(SdkRequest):
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


class ObserveRequest(PaginationParams):
    url: Annotated[
        str | None,
        Field(description="The URL to observe. If not provided, uses the current page URL."),
    ] = None
    instructions: Annotated[
        str | None,
        Field(description="Additional instructions to use for the observation."),
    ] = None
    perception_type: Annotated[
        PerceptionType | None, Field(description="Whether to run with fast or deep perception")
    ] = None


class ObserveRequestDict(PaginationParamsDict, total=False):
    """Request dictionary for observation operations.

    Args:
        url: The URL to observe. If not provided, uses the current page URL.
        instructions: Additional instructions to use for the observation.
    """

    url: str | None
    instructions: str | None
    perception_type: PerceptionType | None


class ScrapeMarkdownParamsDict(TypedDict, total=False):
    """Request dictionary for scraping parameters.

    Args:
        scrape_links: Whether to scrape links from the page. Links are scraped by default.
        scrape_images: Whether to scrape images from the page. Images are not scraped by default.
        only_main_content: Whether to only scrape the main content of the page. If True, navbars, footers, etc. are excluded.
        use_link_placeholders: Whether to use link/image placeholders to reduce the number of tokens in the prompt and hallucinations.
    """

    scrape_links: bool
    scrape_images: bool
    only_main_content: bool
    use_link_placeholders: bool


class ScrapeStructuredParamsDict(TypedDict, total=False):
    """Request dictionary for scraping parameters.

    Args:
        response_format: The response format to use for the scrape. You can use a Pydantic model or a JSON Schema dict.
        instructions: Additional instructions to use for the scrape.
    """


class ScrapeParamsDict(ScrapeMarkdownParamsDict, ScrapeStructuredParamsDict, total=False):
    ignored_tags: list[str] | None
    only_images: bool
    response_format: type[BaseModel] | None
    instructions: str | None


class ScrapeRequestDict(ScrapeParamsDict, total=False):
    """Request dictionary for scraping operations."""

    pass


class ScrapeParams(SdkRequest):
    scrape_links: Annotated[
        bool,
        Field(description="Whether to scrape links from the page. Links are scraped by default."),
    ] = True

    scrape_images: Annotated[
        bool,
        Field(description="Whether to scrape images from the page. Images are scraped by default."),
    ] = False

    ignored_tags: Annotated[list[str] | None, Field(description="HTML tags to ignore from the page")] = None

    only_main_content: Annotated[
        bool,
        Field(
            description=(
                "Whether to only scrape the main content of the page. If True, navbars, footers, etc. are excluded."
            ),
        ),
    ] = True

    only_images: Annotated[
        bool,
        Field(description="Whether to only scrape images from the page. If True, the page content is excluded."),
    ] = False

    response_format: Annotated[
        type[BaseModel] | None,
        Field(
            description="The response format to use for the scrape. You can use a Pydantic model or a JSON Schema dict (cf. https://docs.pydantic.dev/latest/concepts/json_schema/#generating-json-schema.)"
        ),
    ] = None

    instructions: Annotated[
        str | None,
        Field(
            description="Additional instructions to use for the scrape. E.g. 'Extract only the title, date and content of the articles.'"
        ),
    ] = None

    use_link_placeholders: Annotated[
        bool,
        Field(
            description="Whether to use link/image placeholders to reduce the number of tokens in the prompt and hallucinations. However this is an experimental feature and might not work as expected."
        ),
    ] = False

    def requires_schema(self) -> bool:
        return self.response_format is not None or self.instructions is not None

    def removed_tags(self) -> list[str]:
        tags = self.ignored_tags.copy() if self.ignored_tags is not None else []
        if not self.scrape_links:
            tags.append("a")
        if not self.scrape_images:
            tags.append("img")
        return tags

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
        return convert_response_format_to_pydantic_model(value)

    @override
    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        dump = self.model_dump(*args, **kwargs)
        if (
            "response_format" in dump
            and isinstance(self.response_format, type)
            and issubclass(self.response_format, BaseModel)  # pyright: ignore[reportUnnecessaryIsInstance]
        ):
            dump["response_format"] = self.response_format.model_json_schema()
        return json.dumps(dump)


class ScrapeRequest(ScrapeParams):
    pass


class ExecutionRequestDict(TypedDict, total=False):
    """Request dictionary for step operations.

    Args:
        type: The type of action to execute (e.e "click", "fill", etc.)
        id: The ID of the action to execute. Required for step type actions.
        value: The value to input for form actions.
        enter: Whether to press enter after inputting the value.
        action: The action to execute. Cannot be used together with action_id, value, or enter.
    """

    type: str
    id: str | None
    value: str | int | None
    enter: bool | None
    selector: str | NodeSelectors | None


class ExecutionRequest(SdkRequest):
    type: Annotated[str, Field(description="The type of action to execute")]
    id: Annotated[str | None, Field(description="The ID of the action to execute")] = None

    value: Annotated[str | int | None, Field(description="The value to input for form actions")] = None

    enter: Annotated[
        bool | None,
        Field(description="Whether to press enter after inputting the value"),
    ] = None

    selector: Annotated[
        NodeSelectors | None, Field(description="The dom selector to use to find the element to interact with")
    ] = None

    @field_validator("selector", mode="before")
    @classmethod
    def convert_selector(cls, value: str | NodeSelectors | None) -> NodeSelectors | None:
        if value is None:
            return None
        if isinstance(value, str):
            return NodeSelectors.from_unique_selector(value)
        return value

    @field_validator("type", mode="after")
    @classmethod
    def verify_type(cls, value: Any) -> Any:
        valid_keys = BaseAction.ACTION_REGISTRY.keys()
        if value not in valid_keys:
            raise ValueError(f"Invalid action type '{value}'. Valid types are: {valid_keys}")
        return value

    @staticmethod
    def get_action(
        action: ActionUnion | dict[str, Any] | None, data: ExecutionRequestDict | None = None
    ) -> ActionUnion:
        # if provided, return the action
        if isinstance(action, BaseAction):
            # already a valid action
            return action
        if isinstance(action, dict):
            if "selector" in action and "id" not in action:
                action["id"] = ""  # TODO: find a better way to handle this
            return ActionValidation.model_validate({"action": action}).action
        if data is None and action is None:
            raise ValueError("No action provided")

        # otherwise, convert data to action
        action = ExecutionRequest.model_validate(data)
        # otherwise, convert current object to action
        if action.type in BrowserAction.BROWSER_ACTION_REGISTRY:
            return BrowserAction.from_param(action.type, action.value)

        if (action.id is None or action.id == "") and action.selector is None:
            raise ValueError(f"Action '{action.type}' need to provided an action_id or a selector")
        return InteractionAction.from_param(
            action_type=action.type, value=action.value, id=action.id, selector=action.selector
        )


class ExecutionResponseWithSession(ExecutionResult):
    """Used for session.execute calls"""

    session: Annotated[SessionResponse, Field(description="Browser session information")]


class ScrapeResponse(DataSpace):
    session: Annotated[SessionResponse, Field(description="Browser session information")]


class ObserveResponse(Observation):
    session: Annotated[SessionResponse, Field(description="Browser session information")]

    @staticmethod
    def from_obs(obs: Observation, session: SessionResponse) -> "ObserveResponse":
        return ObserveResponse(
            metadata=obs.metadata,
            space=obs.space,
            screenshot=obs.screenshot,
            session=session,
        )


# ############################################################
# Agent endpoints
# ############################################################


class AgentStatus(StrEnum):
    active = "active"
    closed = "closed"


class AgentSessionRequest(SdkRequest):
    agent_id: Annotated[str, Field(description="The ID of the agent to run")]


class AgentCreateRequestDict(TypedDict, total=False):
    """Request dictionary for agent create operations.

    Args:
        session_id: The ID of the session to use.
        reasoning_model: The language model to use for agent reasoning.
        use_vision: Whether to enable vision capabilities for the agent.
        max_steps: Maximum number of steps the agent can take.
        vault_id: Optional ID of the vault to use.
        notifier_config: Config used for the notifier.
    """

    reasoning_model: LlmModel | str
    use_vision: bool
    max_steps: int
    vault_id: str | None
    persona_id: str | None
    notifier_config: dict[str, Any] | None


class SdkAgentCreateRequestDict(AgentCreateRequestDict, total=False):
    session_id: str


class AgentRunRequestDict(TypedDict, total=False):
    """Request dictionary for agent run operations.

    Args:
        task: The task description to execute (required).
        url: Optional URL to process, defaults to None.
        response_format: The response format to use for the agent answer. You can use a Pydantic model or a JSON Schema dict.
        session_offset: [Experimental] The step from which the agent should gather information from in the session. If none, fresh memory
    """

    task: Required[str]
    url: str | None
    response_format: type[BaseModel] | None
    session_offset: int | None


class SdkAgentStartRequestDict(SdkAgentCreateRequestDict, AgentRunRequestDict, total=False):
    """Request dictionary for starting an agent.

    Args:
        session_id: The ID of the session to use.
        reasoning_model: The language model to use for agent reasoning.
        use_vision: Whether to enable vision capabilities for the agent.
        max_steps: Maximum number of steps the agent can take.
        vault_id: Optional ID of the vault to use.
        notifier_config: Config used for the notifier.
        task: The task description to execute.
        url: Optional URL to process.
        response_format: The response format to use for the agent answer.
        session_offset: [Experimental] The step from which the agent should gather information from in the session. If none, fresh memory
    """

    pass


class __AgentCreateRequest(SdkRequest):
    reasoning_model: Annotated[LlmModel | str, Field(description="The reasoning model to use")] = Field(
        default_factory=LlmModel.default
    )
    use_vision: Annotated[
        bool, Field(description="Whether to use vision for the agent. Not all reasoning models support vision.")
    ] = True
    max_steps: Annotated[int, Field(description="The maximum number of steps the agent should take", ge=1, le=50)] = (
        DEFAULT_MAX_NB_STEPS
    )
    vault_id: Annotated[str | None, Field(description="The vault to use for the agent")] = None
    persona_id: Annotated[str | None, Field(description="The persona to use for the agent")] = None
    notifier_config: Annotated[dict[str, Any] | None, Field(description="Config used for the notifier")] = None


# This is only used for local sessions to validate the reasoning model for local .env variables
class AgentCreateRequest(__AgentCreateRequest):
    @field_validator("reasoning_model")
    @classmethod
    def validate_reasoning_model(cls, value: LlmModel) -> LlmModel:
        provider = LlmModel.get_provider(value)
        if not provider.has_apikey_in_env():
            raise ValueError(
                f"Model '{value}' requires the {provider.apikey_name} variable to be configured in the environment"
            )
        return value


class SdkAgentCreateRequest(__AgentCreateRequest):
    session_id: Annotated[
        str,
        Field(description="The ID of the session to run the agent on"),
    ]


class AgentRunRequest(SdkRequest):
    task: Annotated[str, Field(description="The task that the agent should perform")]
    url: Annotated[str | None, Field(description="The URL that the agent should start on (optional)")] = None
    response_format: Annotated[
        type[BaseModel] | None,
        Field(
            description="The response format to use for the agent answer. You can use a Pydantic model or a JSON Schema dict (cf. https://docs.pydantic.dev/latest/concepts/json_schema/#generating-json-schema.)"
        ),
    ] = None
    session_offset: Annotated[
        int | None,
        Field(
            description="[Experimental] The step from which the agent should gather information from in the session. If none, fresh memory"
        ),
    ] = None

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
        return convert_response_format_to_pydantic_model(value)

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        dump = super().model_dump(*args, **kwargs)
        if isinstance(self.response_format, type) and issubclass(self.response_format, BaseModel):  # pyright: ignore[reportUnnecessaryIsInstance]
            dump["response_format"] = self.response_format.model_json_schema()
        return dump

    @override
    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        dump = self.model_dump(*args, **kwargs)
        if isinstance(self.response_format, type) and issubclass(self.response_format, BaseModel):  # pyright: ignore[reportUnnecessaryIsInstance]
            dump["response_format"] = self.response_format.model_json_schema()
        return json.dumps(dump)


class AgentStartRequest(SdkAgentCreateRequest, AgentRunRequest):
    pass


class AgentStatusRequestDict(TypedDict, total=False):
    """Request dictionary for agent status operations.

    Args:
        agent_id: The ID of the agent for which to get the status.
        replay: Whether to include the replay in the response.
    """

    agent_id: Required[Annotated[str, Field(description="The ID of the agent for which to get the status")]]
    replay: bool


class AgentStatusRequest(AgentSessionRequest):
    replay: Annotated[bool, Field(description="Whether to include the replay in the response")] = False


class AgentListRequestDict(SessionListRequestDict, total=False):
    """Request dictionary for listing agents.

    Args:
        only_active: Whether to only list active agents.
        page_size: Number of agents to return per page.
        page: Page number to return.
        only_saved: Whether to only list saved agents.
    """

    only_saved: bool


class AgentListRequest(SessionListRequest):
    only_saved: bool = False


class AgentResponse(SdkResponse):
    agent_id: Annotated[str, Field(description="The ID of the agent")]
    created_at: Annotated[dt.datetime, Field(description="The creation time of the agent")]
    session_id: Annotated[str, Field(description="The ID of the session")]
    status: Annotated[AgentStatus, Field(description="The status of the agent (active or closed)")]
    closed_at: Annotated[dt.datetime | None, Field(description="The closing time of the agent")] = None
    saved: Annotated[bool, Field(description="Whether the agent is saved as a workflow")] = False
    credit_usage: Annotated[
        float | None, Field(description="Credit usage for the agent. None if the agent is still running")
    ] = None


class AgentStatusResponse(AgentResponse, ReplayResponse):
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
        list[dict[str, Any]],
        Field(description="The steps that the agent has currently taken"),
    ] = Field(default_factory=lambda: [])
    replay_start_offset: Annotated[int, Field(description="The start offset of the replay")]
    replay_stop_offset: Annotated[int, Field(description="The stop offset of the replay")]


# ############################################################
# Workflow endpoints
# ############################################################


# Workflow request dictionaries
class CreateWorkflowRequestDict(TypedDict, total=True):
    """Request dictionary for creating a workflow.

    Args:
        workflow_path: The path to the workflow to upload.
    """

    workflow_path: str
    name: NotRequired[str | None]
    description: NotRequired[str | None]
    shared: NotRequired[bool]


class UpdateWorkflowRequestDict(TypedDict):
    """Request dictionary for updating a workflow.

    Args:
        workflow_path: The path to the workflow to upload.
        workflow_id: The ID of the workflow to update.
        version: The version of the workflow to update.
    """

    workflow_path: str
    version: NotRequired[str | None]


class GetWorkflowRequestDict(TypedDict, total=False):
    """Request dictionary for getting a workflow.

    Args:
        workflow_id: The ID of the workflow to get.
        version: The version of the workflow to get.
    """

    version: str | None


class ListWorkflowsRequestDict(SessionListRequestDict, total=False):
    """Request dictionary for listing workflows.

    Args:
        only_active: Whether to only list active workflows.
        page: The page number to list workflows for.
        page_size: The number of workflows to list per page.
    """

    pass


class RunWorkflowRequestDict(TypedDict, total=False):
    """Request dictionary for running a workflow.

    Args:
        version: The version of the workflow to run.
        local: Whether to run the workflow locally.
    """

    workflow_id: str
    variables: dict[str, Any]
    stream: bool


class RunWorkflowRequest(SdkRequest):
    workflow_id: Annotated[str, Field(description="The ID of the workflow to run")]
    variables: Annotated[dict[str, Any], Field(description="The variables to run the workflow with")]
    stream: Annotated[bool, Field(description="Whether to stream logs, or only return final response")] = True


# Workflow request models
class CreateWorkflowRequest(SdkRequest):
    workflow_path: Annotated[str, Field(description="The path to the workflow to upload")]
    name: Annotated[str | None, Field(description="The name of the workflow run")] = None
    description: Annotated[str | None, Field(description="The description of the workflow run")] = None
    shared: Annotated[bool, Field(description="Whether the workflow run is public and shared with other users")] = False


class ForkWorkflowRequest(SdkRequest):
    workflow_id: Annotated[str, Field(description="The ID of the workflow to fork")]


class GetWorkflowResponse(SdkResponse):
    workflow_id: Annotated[str, Field(description="The ID of the workflow")]
    created_at: Annotated[dt.datetime, Field(description="The creation time of the workflow")]
    updated_at: Annotated[dt.datetime, Field(description="The last update time of the workflow")]
    latest_version: Annotated[str, Field(description="The version of the workflow")]
    versions: Annotated[list[str], Field(description="The versions of the workflow")]
    status: Annotated[str, Field(description="The status of the workflow")]
    name: Annotated[str | None, Field(description="The name of the workflow")] = None
    description: Annotated[str | None, Field(description="The description of the workflow")] = None
    shared: Annotated[bool, Field(description="Whether the workflow is public and can beshared with other users")] = (
        False
    )
    reference_workflow_id: Annotated[
        str | None,
        Field(
            description="The ID of the reference workflow (i.e wether the workflow was forked from another workflow or not)"
        ),
    ] = None


class GetWorkflowWithLinkResponse(GetWorkflowResponse, FileLinkResponse):
    pass


class UpdateWorkflowRequest(SdkRequest):
    workflow_path: Annotated[str, Field(description="The path to the workflow to upload")]
    version: Annotated[str | None, Field(description="The version of the workflow to update")] = None


class GetWorkflowRequest(SdkRequest):
    version: Annotated[str | None, Field(description="The version of the workflow to get")] = None


class DeleteWorkflowResponse(SdkResponse):
    status: Annotated[Literal["success", "failure"], Field(description="The status of the deletion")]
    message: Annotated[str, Field(description="The message of the deletion")]


class ListWorkflowsRequest(SessionListRequest):
    pass


class ListWorkflowsResponse(SdkResponse):
    items: Annotated[list[GetWorkflowResponse], Field(description="The workflows")]
    page: Annotated[int, Field(description="Current page number")]
    page_size: Annotated[int, Field(description="Number of items per page")]
    has_next: Annotated[bool, Field(description="Whether there are more pages")]
    has_previous: Annotated[bool, Field(description="Whether there are previous pages")]


# ############################################################
# Workflow run endpoints
# ############################################################


class CreateWorkflowRunRequestDict(TypedDict, total=False):
    local: bool


class CreateWorkflowRunRequest(SdkRequest):
    local: Annotated[bool, Field(description="Whether to run the workflow locally, or in cloud")] = False


class StartWorkflowRunRequest(SdkRequest):
    workflow_id: Annotated[str, Field(description="The ID of the workflow")]
    workflow_run_id: Annotated[str | None, Field(description="The ID of the workflow run")] = None
    variables: Annotated[dict[str, Any] | None, Field(description="The variables to run the workflow with")] = None
    stream: Annotated[bool, Field(description="Whether to stream logs, or only return final response")] = False


WorkflowRunStatus = Literal["closed", "active", "failed"]


class WorkflowRunResponse(SdkResponse):
    workflow_id: Annotated[str, Field(description="The ID of the workflow")]
    workflow_run_id: Annotated[str, Field(description="The ID of the workflow run")]
    session_id: Annotated[str | None, Field(description="The ID of the session")]
    result: Annotated[Any, Field(description="The result of the workflow run")]
    status: Annotated[WorkflowRunStatus, Field(description="The status of the workflow run (closed, active, failed)")]


class GetWorkflowRunResponse(SdkResponse):
    workflow_id: str
    workflow_run_id: str
    created_at: dt.datetime
    updated_at: dt.datetime
    status: WorkflowRunStatus
    session_id: Annotated[str | None, Field(description="The ID of the session")] = None
    logs: Annotated[list[str], Field(description="The logs of the workflow run")] = Field(default_factory=list)
    variables: Annotated[dict[str, Any] | None, Field(description="The variables of the workflow run")] = Field(
        default_factory=dict
    )
    result: Annotated[str | None, Field(description="The result of the workflow run (if any)")] = None
    local: Annotated[bool, Field(description="Whether the workflow has been run locally or on the cloud")] = False


class WorkflowRunUpdateRequestDict(TypedDict, total=False):
    session_id: str | None
    logs: list[str]
    variables: dict[str, Any] | None
    result: Any | None
    status: WorkflowRunStatus


class WorkflowRunUpdateRequest(SdkRequest):
    session_id: Annotated[str | None, Field(description="The ID of the session")] = None
    logs: Annotated[list[str], Field(description="The logs of the workflow run")] = Field(default_factory=list)
    variables: Annotated[dict[str, Any] | None, Field(description="The variables of the workflow run")] = None
    result: Annotated[Any | None, Field(description="The result of the workflow run")] = None
    status: Annotated[WorkflowRunStatus, Field(description="The status of the workflow run")]


class CreateWorkflowRunResponse(SdkResponse):
    workflow_id: str
    workflow_run_id: str
    created_at: dt.datetime
    status: Literal["created"] = "created"


class UpdateWorkflowRunResponse(SdkResponse):
    workflow_id: str
    workflow_run_id: str
    updated_at: dt.datetime
    status: Literal["updated", "stopped"] = "updated"


class ListWorkflowRunsRequestDict(SessionListRequestDict, total=False):
    pass


class ListWorkflowRunsRequest(SessionListRequest):
    pass


class ListWorkflowRunsResponse(SdkResponse):
    items: Annotated[list[GetWorkflowRunResponse], Field(description="The workflow runs")]
    page: Annotated[int, Field(description="Current page number")]
    page_size: Annotated[int, Field(description="Number of items per page")]
    has_next: Annotated[bool, Field(description="Whether there are more pages")]
    has_previous: Annotated[bool, Field(description="Whether there are previous pages")]
