import datetime as dt
import json
import os
from base64 import b64decode, b64encode
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, Generic, Literal, Required, TypeVar

from notte_core.actions import (
    ActionParameter,
    ActionParameterValue,
    ActionUnion,
    BaseAction,
    BrowserAction,
    InteractionAction,
    StepAction,
)
from notte_core.browser.observation import Observation, StepResult
from notte_core.browser.snapshot import TabsData
from notte_core.common.config import BrowserType, LlmModel, PlaywrightProxySettings, config
from notte_core.credentials.base import Credential, CredentialsDict, CreditCardDict, Vault
from notte_core.data.space import DataSpace
from notte_core.utils.pydantic_schema import convert_response_format_to_pydantic_model
from notte_core.utils.url import get_root_domain
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pyotp import TOTP
from typing_extensions import TypedDict, override

# ############################################################
# Session Management
# ############################################################


DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES = 3
DEFAULT_GLOBAL_SESSION_TIMEOUT_IN_MINUTES = 30
DEFAULT_MAX_NB_ACTIONS = 100
DEFAULT_LIMIT_LIST_ITEMS = 10
DEFAULT_MAX_NB_STEPS = config.max_steps

DEFAULT_HEADLESS_VIEWPORT_WIDTH = 1920
DEFAULT_HEADLESS_VIEWPORT_HEIGHT = 1080

DEFAULT_VIEWPORT_WIDTH = config.viewport_width
DEFAULT_VIEWPORT_HEIGHT = config.viewport_height
DEFAULT_BROWSER_TYPE = config.browser_type
DEFAULT_USER_AGENT = config.user_agent
DEFAULT_CHROME_ARGS = config.chrome_args


class SdkBaseModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class ExecutionResponse(SdkBaseModel):
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


class ProxyGeolocation(SdkBaseModel):
    """
    Geolocation settings for the proxy.
    E.g. "New York, NY, US"
    """

    country: ProxyGeolocationCountry
    # TODO: enable city & state later on
    # city: str
    # state: str


class NotteProxy(SdkBaseModel):
    type: Literal["notte"] = "notte"
    geolocation: ProxyGeolocation | None = None
    # TODO: enable domainPattern later on
    # domainPattern: str | None = None

    @staticmethod
    def from_country(country: str) -> "NotteProxy":
        return NotteProxy(geolocation=ProxyGeolocation(country=ProxyGeolocationCountry(country)))


class ExternalProxy(SdkBaseModel):
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


class Cookie(SdkBaseModel):
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

    @staticmethod
    def dump_json(cookies: list["Cookie"], path: str | Path) -> int:
        path = Path(path)
        cookies_dump = [cookie.model_dump() for cookie in cookies]
        return path.write_text(json.dumps(cookies_dump))


class SetCookiesRequest(SdkBaseModel):
    cookies: list[Cookie]

    @staticmethod
    def from_json(path: str | Path) -> "SetCookiesRequest":
        cookies = Cookie.from_json(path)
        return SetCookiesRequest(cookies=cookies)


class SetCookiesResponse(SdkBaseModel):
    success: bool
    message: str


class GetCookiesResponse(SdkBaseModel):
    cookies: list[Cookie]


class ReplayResponse(SdkBaseModel):
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
    headless: bool
    timeout_minutes: int
    proxies: list[ProxySettings] | bool
    browser_type: BrowserType
    user_agent: str | None
    chrome_args: list[str] | None
    viewport_width: int | None
    viewport_height: int | None


class SessionRequestDict(TypedDict, total=False):
    session_id: str | None


class SessionStartRequest(SdkBaseModel):
    headless: Annotated[bool, Field(description="Whether to run the session in headless mode.")] = config.headless

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
    chrome_args: Annotated[list[str] | None, Field(description="Override the chrome instance arguments")] = Field(
        default_factory=lambda: DEFAULT_CHROME_ARGS
    )
    viewport_width: Annotated[int | None, Field(description="The width of the viewport")] = DEFAULT_VIEWPORT_WIDTH
    viewport_height: Annotated[int | None, Field(description="The height of the viewport")] = DEFAULT_VIEWPORT_HEIGHT

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


class SessionRequest(SdkBaseModel):
    session_id: Annotated[
        str | None,
        Field(description="The ID of the session. A new session is created when not provided."),
    ] = None


class SessionStatusRequest(SdkBaseModel):
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


class SessionListRequest(SdkBaseModel):
    only_active: bool = True
    page_size: int = DEFAULT_LIMIT_LIST_ITEMS
    page: int = 1


class SessionResponse(SdkBaseModel):
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
    # TODO: discuss if this is the best way to handle errors
    error: Annotated[str | None, Field(description="Error message if the operation failed to complete")] = None
    proxies: Annotated[
        bool,
        Field(
            description="Whether proxies were used for the session. True if any proxy was applied during session creation."
        ),
    ] = False
    browser_type: BrowserType = BrowserType.CHROMIUM

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


class SessionResponseDict(TypedDict, total=False):
    session_id: str
    timeout_minutes: int
    created_at: dt.datetime
    last_accessed_at: dt.datetime
    duration: dt.timedelta
    closed_at: dt.datetime | None
    status: Literal["active", "closed", "error", "timed_out"]
    error: str | None
    proxies: bool
    browser_type: BrowserType


# ############################################################
# Session debug endpoints
# ############################################################


class TabSessionDebugRequest(SdkBaseModel):
    tab_idx: int


class TabSessionDebugResponse(SdkBaseModel):
    metadata: TabsData
    debug_url: str
    ws_url: str


class WebSocketUrls(SdkBaseModel):
    cdp: Annotated[str, Field(description="WebSocket URL to connect using CDP protocol")]
    recording: Annotated[str, Field(description="WebSocket URL for live session recording (screenshot stream)")]
    logs: Annotated[str, Field(description="WebSocket URL for live logs (obsveration / actions events)")]


class SessionDebugResponse(SdkBaseModel):
    debug_url: str
    ws: WebSocketUrls
    tabs: list[TabSessionDebugResponse]


class SessionDebugRecordingEvent(SdkBaseModel):
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


class EmailsReadRequest(SdkBaseModel):
    limit: Annotated[int, Field(description="Max number of emails to return")] = DEFAULT_LIMIT_LIST_ITEMS
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only emails that are not older than <timedelta>")
    ] = None
    unread_only: Annotated[bool, Field(description="Return only previously unread emails")] = False


class EmailResponse(SdkBaseModel):
    subject: Annotated[str, Field(description="Subject of the email")]
    email_id: Annotated[str, Field(description="Email UUID")]
    created_at: Annotated[dt.datetime, Field(description="Creation date")]
    sender_email: Annotated[str | None, Field(description="Email address of the sender")]
    sender_name: Annotated[str | None, Field(description="Name (if available) of the sender")]
    text_content: Annotated[
        str | None, Field(description="Raw textual body, can be uncorrelated with html content")
    ] = None
    html_content: Annotated[str | None, Field(description="HTML body, can be uncorrelated with raw content")] = None


class SMSReadRequestDict(TypedDict, total=False):
    limit: int
    timedelta: dt.timedelta | None
    unread_only: bool


class SMSReadRequest(SdkBaseModel):
    limit: Annotated[int, Field(description="Max number of messages to return")] = DEFAULT_LIMIT_LIST_ITEMS
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only messages that are not older than <timedelta>")
    ] = None
    unread_only: Annotated[bool, Field(description="Return only previously unread messages")] = False


class SMSResponse(SdkBaseModel):
    body: Annotated[str, Field(description="SMS message body")]
    sms_id: Annotated[str, Field(description="SMS UUID")]
    created_at: Annotated[dt.datetime, Field(description="Creation date")]
    sender: Annotated[str | None, Field(description="SMS sender phone number")]


class PersonaCreateRequestDict(TypedDict, total=False):
    pass


class PersonaCreateRequest(SdkBaseModel):
    pass


class PersonaCreateResponse(SdkBaseModel):
    persona_id: Annotated[str, Field(description="ID of the created persona")]


class VaultCreateRequestDict(TypedDict, total=False):
    pass


class VaultCreateRequest(SdkBaseModel):
    pass


class VaultCreateResponse(SdkBaseModel):
    vault_id: Annotated[str, Field(description="ID of the created vault")]


class ListCredentialsRequestDict(TypedDict, total=False):
    pass


class ListCredentialsRequest(SdkBaseModel):
    pass


class ListCredentialsResponse(SdkBaseModel):
    credentials: Annotated[list[Credential], Field(description="URLs for which we hold credentials")]


class ListVaultsRequestDict(TypedDict, total=False):
    pass


class ListVaultsRequest(SdkBaseModel):
    pass


class ListVaultsResponse(SdkBaseModel):
    vaults: Annotated[list[Vault], Field(description="Vaults owned by the user")]


class VirtualNumberRequestDict(TypedDict, total=False):
    pass


class VirtualNumberRequest(SdkBaseModel):
    pass


class VirtualNumberResponse(SdkBaseModel):
    status: Annotated[str, Field(description="Status of the created virtual number")]


class AddCredentialsRequestDict(CredentialsDict, total=True):
    url: str


def validate_url(value: str | None) -> str | None:
    if value is None:
        return None
    domain_url = get_root_domain(value)
    if len(domain_url) == 0:
        raise ValueError(f"Invalid URL: {value}. Please provide a valid URL with a domain name.")
    return domain_url


class AddCredentialsRequest(SdkBaseModel):
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


class AddCredentialsResponse(SdkBaseModel):
    status: Annotated[str, Field(description="Status of the created credentials")]


class GetCredentialsRequestDict(TypedDict, total=False):
    url: str


class GetCredentialsRequest(SdkBaseModel):
    url: str

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return validate_url(value)


class GetCredentialsResponse(SdkBaseModel):
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
    url: str


class DeleteCredentialsRequest(SdkBaseModel):
    url: str

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return validate_url(value)


class DeleteCredentialsResponse(SdkBaseModel):
    status: Annotated[str, Field(description="Status of the deletion")]


class DeleteVaultRequestDict(TypedDict, total=False):
    pass


class DeleteVaultRequest(SdkBaseModel):
    pass


class DeleteVaultResponse(SdkBaseModel):
    status: Annotated[str, Field(description="Status of the deletion")]


class AddCreditCardRequestDict(CreditCardDict, total=True):
    pass


class AddCreditCardRequest(SdkBaseModel):
    credit_card: Annotated[CreditCardDict, Field(description="Credit card to add")]

    @classmethod
    def from_dict(cls, dic: AddCreditCardRequestDict) -> "AddCreditCardRequest":
        return AddCreditCardRequest(credit_card=dic)


class AddCreditCardResponse(SdkBaseModel):
    status: Annotated[str, Field(description="Status of the created credit card")]


class GetCreditCardRequestDict(TypedDict, total=False):
    pass


class GetCreditCardRequest(SdkBaseModel):
    pass


class GetCreditCardResponse(SdkBaseModel):
    credit_card: Annotated[CreditCardDict, Field(description="Retrieved credit card")]


class DeleteCreditCardRequestDict(TypedDict, total=False):
    pass


class DeleteCreditCardRequest(SdkBaseModel):
    pass


class DeleteCreditCardResponse(SdkBaseModel):
    status: Annotated[str, Field(description="Status of the deletion")]


# ############################################################
# Environment endpoints
# ############################################################


class PaginationParamsDict(TypedDict, total=False):
    min_nb_actions: int | None
    max_nb_actions: int


class PaginationParams(SdkBaseModel):
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


class ObserveRequestDict(PaginationParamsDict, total=False):
    url: str | None
    instructions: str | None


class ScrapeParamsDict(TypedDict, total=False):
    scrape_links: bool
    scrape_images: bool
    only_main_content: bool
    response_format: type[BaseModel] | None
    instructions: str | None
    use_llm: bool | None
    use_link_placeholders: bool


class ScrapeRequestDict(ScrapeParamsDict, total=False):
    url: str | None


class ScrapeParams(SdkBaseModel):
    scrape_links: Annotated[
        bool,
        Field(description="Whether to scrape links from the page. Links are scraped by default."),
    ] = True

    scrape_images: Annotated[
        bool,
        Field(description="Whether to scrape images from the page. Images are scraped by default."),
    ] = False

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

    use_llm: Annotated[
        bool | None,
        Field(
            description=(
                "Whether to use an LLM for the extraction process. This will result in a longer response time but a"
                " better accuracy. If not provided, the default value is the same as the NotteSession config."
            )
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


class ScrapeRequest(ScrapeParams):
    url: Annotated[
        str | None,
        Field(description="The URL to scrape. If not provided, uses the current page URL."),
    ] = None


class StepRequestDict(PaginationParamsDict, total=False):
    type: str
    selector: str | None
    action_id: str | None
    value: str | int | None
    enter: bool | None
    action: StepAction | ActionUnion | None


class StepRequest(PaginationParams):
    type: str = "step"
    action_id: Annotated[str | None, Field(description="The ID of the action to execute")] = None
    selector: str | None = None

    value: Annotated[str | int | None, Field(description="The value to input for form actions")] = None

    enter: Annotated[
        bool | None,
        Field(description="Whether to press enter after inputting the value"),
    ] = None

    action: Annotated[StepAction | ActionUnion | None, Field(description="The action to execute")] = None

    @override
    def model_post_init(self, context: Any, /) -> None:
        if self.action is None:
            value: ActionParameterValue | None = None
            param: ActionParameter | None = None
            if isinstance(self.value, str):
                value = ActionParameterValue(name="value", value=self.value)
                param = ActionParameter(name="value", type=type(self.value).__name__)
            if self.type == "step":
                if self.action_id is None:
                    raise ValueError("Step action need to provide an action_id")
                if self.action_id == "":
                    raise ValueError("Step action has to provide a non-empty action_id")
                self.action = StepAction(
                    id=self.action_id,
                    description="ID only",
                    param=param,
                    value=value,
                    press_enter=self.enter,
                )
            elif self.type in BrowserAction.BROWSER_ACTION_REGISTRY:
                self.action = BrowserAction.from_param(self.type, self.value)

            elif self.type in InteractionAction.INTERACTION_ACTION_REGISTRY:
                self.action = InteractionAction.from_param(self.type, self.value, self.selector)

            else:
                raise ValueError(
                    f"Invalid action type: {self.type}. Valid types are: {BrowserAction.ACTION_REGISTRY.keys()}"
                )
        elif self.action_id is not None:
            raise ValueError("action_id is not allowed when action is provided")
        elif self.value is not None:
            raise ValueError("value is not allowed when action is provided")
        elif self.enter is not None:
            raise ValueError("enter is not allowed when action is provided")

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        dump = super().model_dump(*args, **kwargs)
        if self.action is not None:
            del dump["type"]
            if "action_id" in dump:
                del dump["action_id"]
            if "value" in dump:
                del dump["value"]
            if "enter" in dump:
                del dump["enter"]
        return dump


class StepResponse(StepResult):
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
            data=obs.data,
            progress=obs.progress,
            screenshot=obs.screenshot,
            session=session,
        )


# ############################################################
# Agent endpoints
# ############################################################


class AgentStatus(StrEnum):
    active = "active"
    closed = "closed"


class AgentSessionRequest(SdkBaseModel):
    agent_id: Annotated[str, Field(description="The ID of the agent to run")]


class AgentCreateRequestDict(SessionRequestDict, total=False):
    reasoning_model: LlmModel
    use_vision: bool
    max_steps: int
    vault_id: str | None
    notifier_config: dict[str, Any] | None


class AgentRunRequestDict(TypedDict, total=False):
    task: Required[str]
    url: str | None
    response_format: type[BaseModel] | None


class AgentStartRequestDict(AgentCreateRequestDict, AgentRunRequestDict, total=False):
    pass


class AgentCreateRequest(SessionRequest):
    reasoning_model: Annotated[LlmModel, Field(description="The reasoning model to use")] = Field(
        default_factory=LlmModel.default
    )
    use_vision: Annotated[
        bool, Field(description="Whether to use vision for the agent. Not all reasoning models support vision.")
    ] = True
    max_steps: Annotated[int, Field(description="The maximum number of steps the agent should take")] = (
        DEFAULT_MAX_NB_STEPS
    )
    vault_id: Annotated[str | None, Field(description="The vault to use for the agent")] = None
    notifier_config: Annotated[dict[str, Any] | None, Field(description="Config used for the notifier")] = None


class AgentRunRequest(SdkBaseModel):
    task: Annotated[str, Field(description="The task that the agent should perform")]
    url: Annotated[str | None, Field(description="The URL that the agent should start on (optional)")] = None
    response_format: Annotated[
        type[BaseModel] | None,
        Field(
            description="The response format to use for the agent answer. You can use a Pydantic model or a JSON Schema dict (cf. https://docs.pydantic.dev/latest/concepts/json_schema/#generating-json-schema.)"
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


class AgentStartRequest(AgentCreateRequest, AgentRunRequest):
    pass


class AgentStatusRequestDict(TypedDict, total=False):
    agent_id: Required[Annotated[str, Field(description="The ID of the agent for which to get the status")]]
    replay: bool


class AgentStatusRequest(AgentSessionRequest):
    replay: Annotated[bool, Field(description="Whether to include the replay in the response")] = False


class AgentListRequestDict(SessionListRequestDict, total=False):
    only_saved: bool


class AgentListRequest(SessionListRequest):
    only_saved: bool = False


class AgentStopRequest(AgentSessionRequest, ReplayResponse):
    success: Annotated[bool, Field(description="Whether the agent task was successful")] = False
    answer: Annotated[str, Field(description="The answer to the agent task")] = "Agent manually stopped by user"


class AgentResponse(SdkBaseModel):
    agent_id: Annotated[str, Field(description="The ID of the agent")]
    created_at: Annotated[dt.datetime, Field(description="The creation time of the agent")]
    session_id: Annotated[str, Field(description="The ID of the session")]
    status: Annotated[AgentStatus, Field(description="The status of the agent (active or closed)")]
    closed_at: Annotated[dt.datetime | None, Field(description="The closing time of the agent")] = None


TStepOutput = TypeVar("TStepOutput", bound=BaseModel)


class AgentStatusResponse(AgentResponse, ReplayResponse, Generic[TStepOutput]):
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


def render_agent_status(
    status: str,
    summary: str,
    goal_eval: str,
    memory: str,
    next_goal: str,
    action_str: str,
    colors: bool = True,
) -> list[tuple[str, dict[str, str]]]:
    status_emoji: str
    match status:
        case "success":
            status_emoji = "✅"
        case "failure":
            status_emoji = "❌"
        case _:
            status_emoji = "❓"

    def surround_tags(s: str, tags: tuple[str, ...] = ("b", "blue")) -> str:
        if not colors:
            return s

        start = "".join(f"<{tag}>" for tag in tags)
        end = "".join(f"</{tag}>" for tag in reversed(tags))
        return f"{start}{s}{end}"

    to_log: list[tuple[str, dict[str, str]]] = [
        (surround_tags("📝 Current page:") + " {page_summary}", dict(page_summary=summary)),
        (
            surround_tags("🔬 Previous goal:") + " {emoji} {eval}",
            dict(emoji=status_emoji, eval=goal_eval),
        ),
        (surround_tags("🧠 Memory:") + " {memory}", dict(memory=memory)),
        (surround_tags("🎯 Next goal:") + " {goal}", dict(goal=next_goal)),
        (surround_tags("⚡ Taking action:") + "\n{action_str}", dict(action_str=action_str)),
    ]
    return to_log
