"""Runtime-only 1.x import aliases. Delete this file and its activation import in 3.0."""

import importlib
import sys
import types
import warnings
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import LazyLoader, module_from_spec
from typing import Any, final

from typing_extensions import override

_MODULE_ALIASES: dict[str, str] = {
    "notte_core.errors.actions": "notte_core.errors",
    "notte_core.errors.base": "notte_core.errors",
    "notte_core.errors.llm": "notte_core.errors",
    "notte_core.errors.processing": "notte_core.errors",
    "notte_core.errors.provider": "notte_core.errors",
    "notte_core.common": "notte_core.resource",
    "notte_core.common.config": "notte_core.config",
    "notte_core.common.logging": "notte_core.logging",
    "notte_core.common.cache": "notte_core.cache",
    "notte_core.common.resource": "notte_core.resource",
    "notte_core.common.telemetry": "notte_core.telemetry",
    "notte_core.common.types": "notte_core.schema",
    "notte_core.browser.observation": "notte_core.observation",
    "notte_core.browser.dom_tree": "notte_core.dom_tree",
    "notte_core.browser.highlighter": "notte_core.highlighter",
    "notte_core.browser.node_type": "notte_core.node_type",
    "notte_core.browser.snapshot": "notte_core.snapshot",
    "notte_core.data.fetch": "notte_core.fetch",
    "notte_core.data.space": "notte_core.data",
    "notte_core.ast": "notte_core.types",
    "notte_core.utils.files": "notte_core.config",
    "notte_core.utils.image": "notte_core.observation",
    "notte_core.utils.pydantic_schema": "notte_core.schema",
    "notte_core.utils.raw_file": "notte_core.raw_file",
    "notte_core.utils.singleton": "notte_core.resource",
    "notte_core.utils.url": "notte_core.url",
}

# Only stdlib modules actually re-exported by the corresponding 1.9.7 module.
_STDLIB_REEXPORTS: dict[str, dict[str, str]] = {
    "notte_core.errors.base": {"contextlib": "contextlib"},
    "notte_core.errors.processing": {"re": "re"},
    "notte_core.common.config": {"os": "os"},
    "notte_core.common.logging": {"time": "time"},
    "notte_core.common.cache": {
        "getpass": "getpass",
        "os": "os",
        "platform": "platform",
        "tempfile": "tempfile",
        "threading": "threading",
    },
    "notte_core.common.telemetry": {
        "metadata": "importlib.metadata",
        "inspect": "inspect",
        "logging": "logging",
        "os": "os",
        "platform": "platform",
        "uuid": "uuid",
    },
    "notte_core.browser.observation": {"base64": "base64", "dt": "datetime", "io": "io"},
    "notte_core.browser.dom_tree": {"time": "time"},
    "notte_core.browser.highlighter": {"io": "io"},
    "notte_core.browser.snapshot": {"dt": "datetime"},
    "notte_core.data.fetch": {"base64": "base64", "io": "io", "json": "json"},
    "notte_core.ast": {"ast": "ast", "json": "json", "traceback": "traceback", "types": "types"},
    "notte_core.utils.files": {"json": "json"},
    "notte_core.utils.image": {"io": "io", "os": "os", "textwrap": "textwrap"},
    "notte_core.utils.pydantic_schema": {"dt": "datetime"},
    "notte_core.utils.raw_file": {"dt": "datetime", "mimetypes": "mimetypes", "re": "re"},
    "notte_core.utils.url": {"socket": "socket"},
}


# Reject unknown names before importing: inspection tools scan sys.modules with hasattr.
_PUBLIC_NAMES: dict[str, frozenset[str]] = {
    "notte_core.errors.actions": frozenset(
        (
            "ActionError ActionExecutionError EvaluateJsNoDataError EvaluateJsResultLimitError "
            + "FetchResponseDecodeError InvalidActionError NoCredentialsFoundError NotteBaseError"
        ).split()
    ),
    "notte_core.errors.base": frozenset(
        "ClassVar Enum ErrorConfig ErrorMessageMode ErrorMode Literal NotteBaseError NotteTimeoutError".split()
    ),
    "notte_core.errors.llm": frozenset(
        "InvalidPromptTemplateError LLMParsingError LLmModelOverloadedError NotteBaseError".split()
    ),
    "notte_core.errors.processing": frozenset(
        (
            "CredentialFieldValidationError InvalidInternalCheckError InvalidPlaceholderError NotteBaseError "
            + "ScrapeFailedError SnapshotProcessingError"
        ).split()
    ),
    "notte_core.errors.provider": frozenset(
        (
            "ContextWindowExceededError InsufficentCreditsError InvalidAPIKeyError "
            + "InvalidJsonResponseForStructuredOutput LLMProviderError MissingAPIKeyForModel "
            + "ModelDoesNotSupportImageError ModelNotFoundError NotteBaseError RateLimitError "
            + "UnsupportedResponseSchemaError"
        ).split()
    ),
    "notte_core.common": frozenset("AsyncResource SyncResource".split()),
    "notte_core.common.config": frozenset(
        (
            "Any BaseModel BrowserBackend BrowserType CookieDict DEFAULT_CONFIG_PATH ErrorMode Field Literal "
            + "NotteConfig NotteConfigDict Path PerceptionType PlaywrightProxySettings RaiseCondition Required "
            + "Self StrEnum TomlConfig TypedDict Unpack computed_field config override"
        ).split()
    ),
    "notte_core.common.logging": frozenset("Any Callable F TypeVar annotations get_logger logger timeit".split()),
    "notte_core.common.cache": frozenset(
        "CacheDirectory Enum Path ensure_cache_directory get_cache_root logger".split()
    ),
    "notte_core.common.resource": frozenset("ABC AsyncResource Self SyncResource TracebackType abstractmethod".split()),
    "notte_core.common.telemetry": frozenset(
        (
            "Any CacheDirectory Callable DEBUG_LOGGING DISABLE_TELEMETRY F POSTHOG_API_KEY "
            + "POSTHOG_EVENT_SETTINGS POSTHOG_HOST Path SCARF_GATEWAY_URL TypeVar capture_event "
            + "ensure_cache_directory get_or_create_installation_id get_system_info logger setup_posthog "
            + "setup_scarf track_package_download track_usage version wraps"
        ).split()
    ),
    "notte_core.common.types": frozenset("BaseModel TResponseFormat TypeVar".split()),
    "notte_core.browser.observation": frozenset(
        (
            "ActionSpace ActionUnion Annotated Any BaseModel BoundingBox BrowserSnapshot BytesIO ConfigDict "
            + "DataSpace ExecutionResult Field FilledTimedSpan Iterator NotteBaseError Observation Screenshot "
            + "SerializedError SnapshotMetadata TimedSpan ViewportData b64decode b64encode clean_url "
            + "contextmanager dedent field_validator logger model_validator override utc_now"
        ).split()
    ),
    "notte_core.browser.dom_tree": frozenset(
        (
            "AttributeValue AttributeValues BaseModel BoundingBox Callable ClassVar ComputedDomAttributes "
            + "DomAttributes DomNode NodeRole NodeSelectors NodeType Sequence TypeAlias dataclass field logger "
            + "override"
        ).split()
    ),
    "notte_core.browser.highlighter": frozenset(
        "BoundingBox Enum LabelConfig LabelPosition Rectangle dataclass profiler".split()
    ),
    "notte_core.browser.node_type": frozenset("Enum NodeRole NodeType logger".split()),
    "notte_core.browser.snapshot": frozenset(
        (
            "BaseModel BrowserSnapshot DomNode Field Sequence SnapshotMetadata TabsData ViewportData b64encode "
            + "clean_url"
        ).split()
    ),
    "notte_core.data.fetch": frozenset(
        (
            "Any CaseInsensitiveDict FetchData FetchResponseDecodeError HTTPStatus Mapping annotations "
            + "build_fetch_script cast response_from_evaluated urlencode urlsplit urlunsplit"
        ).split()
    ),
    "notte_core.data.space": frozenset(
        (
            "Annotated Any BaseModel DataSpace DictBaseModel Field Generic NoStructuredData RootModel "
            + "ScrapeFailedError Self StructuredData TBaseModel TypeVar model_serializer model_validator"
        ).split()
    ),
    "notte_core.ast": frozenset("Any BaseModel ClassVar ConfigDict Literal ParameterInfo cast override".split()),
    "notte_core.utils.files": frozenset("CookieDict Path create_or_append_cookies_to_file logger".split()),
    "notte_core.utils.image": frozenset("Any b64encode image_from_bytes".split()),
    "notte_core.utils.pydantic_schema": frozenset(
        (
            "Any BaseModel CONSTRAINT_MAPPING ClassVar ConfigDict Field FieldType InvalidResponseFormat "
            + "JsonResponseFormat Literal NotteBaseError Optional SchemaProperty StrEnum TYPE_MAPPING Union cast "
            + "convert_response_format_to_pydantic_model create_model create_model_from_schema field_serializer "
            + "field_validator get_field_params_from_field_schema model_validator override"
        ).split()
    ),
    "notte_core.utils.raw_file": frozenset(
        (
            "Any ComputedDomAttributes DEFAULT_RAW_FILE_SELECTORS DomAttributes DomNode NodeRole NodeSelectors "
            + "NodeType get_empty_dom_node get_file_ext get_filename match_extension parse_qs urlparse"
        ).split()
    ),
    "notte_core.utils.singleton": frozenset("Any Singleton override".split()),
    "notte_core.utils.url": frozenset("clean_url get_root_domain is_valid_url urlparse".split()),
}


@final
class _AliasModule(types.ModuleType):
    def __init__(self, old: str, new: str) -> None:
        super().__init__(old)
        is_package = any(path.startswith(old + ".") for path in _MODULE_ALIASES)
        self.__spec__ = ModuleSpec(old, loader=None, is_package=is_package)
        if is_package:
            self.__path__ = []
        self.__all__ = sorted(_PUBLIC_NAMES[old] | _STDLIB_REEXPORTS.get(old, {}).keys())
        self._new = new
        self._warned = False

    @override
    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(self.__all__))

    @override
    def __getattr__(self, name: str) -> Any:
        if name not in _PUBLIC_NAMES[self.__name__] and name not in _STDLIB_REEXPORTS.get(self.__name__, {}):
            raise AttributeError(name)
        target = importlib.import_module(self._new)
        try:
            value = getattr(target, name)
        except AttributeError:
            stdlib = _STDLIB_REEXPORTS.get(self.__name__, {}).get(name)
            if stdlib is None:
                raise AttributeError(
                    f"module {self.__name__!r} has no attribute {name!r} (removed in notte 2.0)"
                ) from None
            value = importlib.import_module(stdlib)
        if not self._warned:
            self._warned = True
            warnings.warn(
                f"`{self.__name__}` is deprecated and will be removed in notte 3.0; import from `{self._new}` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return value


def install() -> None:
    root = sys.modules["notte_core"]
    for old, new in _MODULE_ALIASES.items():
        parent, _, name = old.rpartition(".")
        if parent not in sys.modules:
            spec = PathFinder.find_spec(parent, root.__path__)
            if spec is None:
                package = types.ModuleType(parent)
                package.__path__ = []
                package.__spec__ = ModuleSpec(parent, loader=None, is_package=True)
            else:
                # Keep real parents real, deferring their normal loader until first use.
                assert spec.loader is not None
                spec.loader = LazyLoader(spec.loader)
                package = module_from_spec(spec)
                sys.modules[parent] = package
                spec.loader.exec_module(package)
            sys.modules[parent] = package
            setattr(root, parent.rpartition(".")[2], package)
        alias = sys.modules.setdefault(old, _AliasModule(old, new))
        setattr(sys.modules[parent], name, alias)


install()
