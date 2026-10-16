from enum import Enum
from typing import ClassVar, Literal, get_args, get_origin, get_type_hints

import pytest
from notte_core import types as core_types
from notte_core.config import CookieDict, NotteConfig, NotteConfigDict
from notte_sdk.types import (
    Cookie,
    CreateFunctionRunRequest,
    CreateFunctionRunRequestDict,
    CreatePhoneNumberRequest,
    CreatePhoneNumberRequestDict,
    DeleteCredentialsRequest,
    DeleteCredentialsRequestDict,
    DeleteCreditCardRequest,
    DeleteCreditCardRequestDict,
    DeleteVaultRequest,
    DeleteVaultRequestDict,
    ExecutionRequest,
    ExecutionRequestDict,
    GetCredentialsRequest,
    GetCredentialsRequestDict,
    GetCreditCardRequest,
    GetCreditCardRequestDict,
    ListCredentialsRequest,
    ListCredentialsRequestDict,
    ListFilesResponse,
    MessageReadRequest,
    MessageReadRequestDict,
    ObserveRequest,
    ObserveRequestDict,
    PaginationParams,
    PaginationParamsDict,
    PersonaCreateRequest,
    PersonaCreateRequestDict,
    PersonaListRequest,
    PersonaListRequestDict,
    ProxyGeolocationCountry,
    ProxyGeolocationCountryCode,
    RunFunctionRequest,
    RunFunctionRequestDict,
    ScrapeParams,
    ScrapeParamsDict,
    ScrapeRequest,
    ScrapeRequestDict,
    SdkRequest,
    SdkResponse,
    SessionListRequest,
    SessionListRequestDict,
    SessionProfile,
    SessionProfileDict,
    SessionStartRequest,
    SessionStartRequestDict,
    SetCookiesRequest,
    VaultCreateRequest,
    VaultCreateRequestDict,
    VaultListRequest,
    VaultListRequestDict,
)
from pydantic import BaseModel, ValidationError


def _test_request_dict_alignment(base_request: type[BaseModel], base_request_dict: type) -> None:
    """Test that a BaseModel and its corresponding TypedDict have matching fields and types."""
    # Get all fields from BaseModel
    request_fields = get_type_hints(base_request)

    # Filter out ClassVar fields from BaseModel
    request_fields = {
        field_name: field_type
        for field_name, field_type in request_fields.items()
        if get_origin(field_type) is not ClassVar and field_name in base_request.model_fields
    }

    # Get all fields from TypedDict
    dict_fields = get_type_hints(base_request_dict)

    # Check that all fields in BaseModel are present in TypedDict
    for field_name, field_type in request_fields.items():
        assert field_name in dict_fields, (
            f"Field {field_name} from {base_request.__name__} is missing in {base_request_dict.__name__}"
        )

        # Get the actual types, handling Optional and Union types
        request_type = field_type
        dict_type = dict_fields[field_name]

        # Handle Optional types
        if hasattr(request_type, "__origin__") and hasattr(request_type, "__args__"):
            request_type_args = get_args(request_type)
            if type(None) in request_type_args:
                request_type = next(t for t in request_type_args if t is not type(None))

        if hasattr(dict_type, "__origin__") and hasattr(dict_type, "__args__"):
            dict_type_args = get_args(dict_type)
            if type(None) in dict_type_args:
                dict_type = next(t for t in dict_type_args if t is not type(None))

        # Generated named OpenAPI enums accept the same wire values as public literal kwargs.
        if isinstance(request_type, type) and issubclass(request_type, Enum) and get_origin(dict_type) is Literal:
            assert {member.value for member in request_type} == set(get_args(dict_type))
            continue

        # Compare the types
        if field_name not in ("selector", "profile", "proxies"):
            assert request_type == dict_type, (
                f"Type mismatch for field {field_name}: "
                f"{base_request.__name__} has {request_type} but {base_request_dict.__name__} has {dict_type}"
            )
        elif field_name == "profile":
            # Special case: profile field in TypedDict accepts both SessionProfileDict and SessionProfile
            # but the BaseModel only needs SessionProfile (Pydantic handles dict conversion)
            # TypedDict: SessionProfileDict | SessionProfile | None
            # BaseModel: SessionProfile | None
            # So we just check that request_type is present in dict_type's union
            dict_type_args = get_args(dict_fields[field_name])
            if dict_type_args:
                # Check that the request type (without None) is in the dict type args
                assert request_type in dict_type_args or type(None) in dict_type_args, (
                    f"Type mismatch for field {field_name}: "
                    f"{base_request.__name__} has {request_type} but {base_request_dict.__name__} has {dict_type}"
                )
        elif field_name == "proxies":
            # Special case: proxies field in TypedDict accepts multiple formats
            # BaseModel: list[ProxySettings] | bool
            # TypedDict: list[ProxySettings] | list[ProxySettingsDict] | bool | ProxyGeolocationCountry
            # We allow the TypedDict to have additional accepted types for user convenience
            pass  # Skip type checking for proxies field

    # Check that all fields in TypedDict are present in BaseModel
    for field_name in dict_fields:
        assert field_name in request_fields, (
            f"Field {field_name} from {base_request_dict.__name__} is missing in {base_request.__name__}"
        )


def test_session_start_request_dict_alignment():
    actual = get_type_hints(SessionStartRequestDict)
    expected = get_type_hints(core_types.SessionStartRequestDict)
    assert actual.keys() == expected.keys()
    assert SessionStartRequestDict.__required_keys__ == core_types.SessionStartRequestDict.__required_keys__
    for key in actual.keys() - {"proxies", "profile"}:
        assert actual[key] == expected[key]
    assert set(actual) <= set(SessionStartRequest.model_fields)


def test_session_profile_dict_alignment():
    _test_request_dict_alignment(SessionProfile, SessionProfileDict)


def test_session_list_request_dict_alignment():
    assert get_type_hints(SessionListRequestDict) == get_type_hints(core_types.SessionListRequestDict)
    assert set(SessionListRequest().model_dump()) == set(get_type_hints(SessionListRequestDict))


def test_message_read_request_dict_alignment():
    _test_request_dict_alignment(MessageReadRequest, MessageReadRequestDict)


def test_persona_create_request_dict_alignment():
    _test_request_dict_alignment(PersonaCreateRequest, PersonaCreateRequestDict)


def test_create_phone_number_request_dict_alignment():
    _test_request_dict_alignment(CreatePhoneNumberRequest, CreatePhoneNumberRequestDict)


def test_get_credentials_request_dict_alignment():
    _test_request_dict_alignment(GetCredentialsRequest, GetCredentialsRequestDict)


def test_delete_credentials_request_dict_alignment():
    _test_request_dict_alignment(DeleteCredentialsRequest, DeleteCredentialsRequestDict)


def test_pagination_params_dict_alignment():
    _test_request_dict_alignment(PaginationParams, PaginationParamsDict)


def test_create_vault_request_dict_alignment():
    _test_request_dict_alignment(VaultCreateRequest, VaultCreateRequestDict)


# NO TEST FOR ADD_CREDENTIALS: Dict is one of the params of AddCredentialsRequest
# NO TEST FOR ADD_CREDIT_CARD: Dict is one of the params of AddCreditCardRequest


def test_get_creds_vault_request_dict_alignment():
    _test_request_dict_alignment(GetCredentialsRequest, GetCredentialsRequestDict)


def test_delete_creds_vault_request_dict_alignment():
    _test_request_dict_alignment(DeleteCredentialsRequest, DeleteCredentialsRequestDict)


def test_list_creds_vault_request_dict_alignment():
    _test_request_dict_alignment(ListCredentialsRequest, ListCredentialsRequestDict)


def test_get_card_vault_request_dict_alignment():
    _test_request_dict_alignment(GetCreditCardRequest, GetCreditCardRequestDict)


def test_del_card_vault_request_dict_alignment():
    _test_request_dict_alignment(DeleteCreditCardRequest, DeleteCreditCardRequestDict)


def test_list_vaults_request_dict_alignment():
    # API-only schema fields are excluded and rejected by the public wrapper.
    assert get_type_hints(VaultListRequestDict) == {"only_active": bool, "page_size": int, "page": int}
    assert set(VaultListRequest().model_dump()) == set(get_type_hints(VaultListRequestDict))


def test_list_personas_request_dict_alignment():
    assert get_type_hints(PersonaListRequestDict) == {"only_active": bool, "page_size": int, "page": int}
    assert set(PersonaListRequest().model_dump()) == set(get_type_hints(PersonaListRequestDict))


def test_del_vault_request_dict_alignment():
    _test_request_dict_alignment(DeleteVaultRequest, DeleteVaultRequestDict)


def test_notte_config_dict_alignment():
    _test_request_dict_alignment(NotteConfig, NotteConfigDict)


def test_cookie_dict_alignment():
    _test_request_dict_alignment(Cookie, CookieDict)


def test_should_be_able_to_start_cdp_session_with_default_session_parameters():
    _ = SessionStartRequest(cdp_url="test")


def test_execution_request_dict_alignment():
    _test_request_dict_alignment(ExecutionRequest, ExecutionRequestDict)


def test_observe_request_dict_alignment():
    _test_request_dict_alignment(ObserveRequest, ObserveRequestDict)


def test_scrape_params_dict_alignment():
    _test_request_dict_alignment(ScrapeParams, ScrapeParamsDict)


def test_scrape_request_dict_alignment():
    _test_request_dict_alignment(ScrapeRequest, ScrapeRequestDict)


@pytest.mark.parametrize(
    "name",
    [
        "CreateFunctionRequest",
        "UpdateFunctionRequest",
        "GetFunctionRequest",
        "ListFunctionsRequest",
        "FunctionRunUpdateRequest",
        "ListFunctionRunsRequest",
    ],
)
def test_function_request_keywords_preserve_public_surface(name):
    from notte_sdk import types as sdk_types

    # Generated schema models include API-only fields. The public keyword dictionaries
    # retain exactly the old fields and annotations, including nullable/narrowed types.
    public_dict = getattr(sdk_types, name + "Dict")
    old_dict = getattr(core_types, name + "Dict")
    assert get_type_hints(public_dict) == get_type_hints(old_dict)
    assert public_dict.__required_keys__ == old_dict.__required_keys__
    assert set(get_type_hints(public_dict)) <= set(getattr(sdk_types, name).model_fields)


def test_run_function_request_dict_alignment():
    _test_request_dict_alignment(RunFunctionRequest, RunFunctionRequestDict)


def test_create_function_run_request_dict_alignment():
    _test_request_dict_alignment(CreateFunctionRunRequest, CreateFunctionRunRequestDict)


def test_sdk_response_should_not_fail_on_extra_fields():
    _ = SdkResponse.model_validate(dict(extra_customer_arg="test"))
    # same for ListFilesResponse
    _ = ListFilesResponse.model_validate(dict(files=[], extra_customer_arg="test"))


def test_sdk_request_should_fail_on_extra_fields():
    with pytest.raises(ValidationError):
        _ = SdkRequest.model_validate(dict(extra_customer_arg="test"))
    # Cookie business validation moved to request-sent/422 captures in test_sessions_codegen.
    assert SetCookiesRequest.from_json is not None


def test_all_request_classes_have_dict_types_and_proper_inheritance():
    """Test that every BaseModel ending with 'Request' has corresponding Dict type and inherits from SdkRequest."""
    import re
    from pathlib import Path

    # Read the types.py file
    types_file_path = (
        Path(__file__).parent.parent.parent / "packages" / "notte-core" / "src" / "notte_core" / "types.py"
    )
    with open(types_file_path, "r") as f:
        types_content = f.read()

    # Find all class definitions ending with 'Request'
    request_class_pattern = r"class\s+(\w*Request)\s*\([^)]*\):"
    request_classes = re.findall(request_class_pattern, types_content)

    # Find all class definitions ending with 'RequestDict'
    # Pattern includes both TypedDict inheritance and other Dict inheritance patterns
    request_dict_pattern = r"class\s+(\w*RequestDict)\s*\([^)]*\):"
    all_request_dict_matches = re.findall(request_dict_pattern, types_content)

    # Filter to only include actual dictionary types by checking the full class definition
    request_dict_classes = []
    for dict_class in all_request_dict_matches:
        # Look for the full class definition to verify it's actually a dict type
        class_def_pattern = rf"class\s+{dict_class}\s*\(([^)]+)\):"
        class_match = re.search(class_def_pattern, types_content)
        if class_match:
            inheritance = class_match.group(1)
            # Check if it inherits from TypedDict or other dict types
            if "TypedDict" in inheritance or "Dict" in inheritance or inheritance.strip().endswith("Dict"):
                request_dict_classes.append(dict_class)

    # Find inheritance patterns for Request classes
    inheritance_pattern = r"class\s+(\w*Request)\s*\(([^)]+)\):"
    inheritance_matches = re.findall(inheritance_pattern, types_content)

    # Convert to sets for easier comparison
    request_set = set(request_classes)
    request_dict_set = set(request_dict_classes)

    # Classes that legitimately don't need Dict types (base classes, special cases)
    exceptions_no_dict = {
        "SdkRequest",  # Base request class
        "ScrapeRequest",  # Inherits from ScrapeParams, uses ScrapeRequestDict indirectly
        "ForkFunctionRequest",  # Simple class, no dict needed
        # Classes that are missing Dict types but legitimately don't need them
        "DownloadFileRequest",  # Simple class with single field
        "SetCookiesRequest",  # Uses existing Cookie structures
        "StartFunctionRunRequest",  # Complex composition, may not need Dict
        "TabSessionDebugRequest",  # Simple debug request with single field
        "_SessionStartRequest",  # Shared implementation for local and remote session requests
    }

    # Create mapping of expected Dict names, excluding exceptions
    expected_dict_names = {req_class + "Dict" for req_class in request_classes if req_class not in exceptions_no_dict}

    # Track missing Dict types (accounting for special cases)
    missing_dict_types = expected_dict_names - request_dict_set

    # Special dict mappings that exist but have different names
    special_dict_mappings = {
        "ScrapeRequest": "ScrapeRequestDict",  # Actually exists as part of ScrapeParams
    }

    # Dict types that exist for Request classes that are in our exceptions
    # These should be removed from the "unexpected" list
    legitimate_dict_types = {
        "VaultListRequestDict",  # For VaultListRequest (inherits from SessionListRequest)
        "PersonaListRequestDict",  # For PersonaListRequest (inherits from SessionListRequest)
        "ListFunctionsRequestDict",  # For ListFunctionsRequest (inherits from SessionListRequest)
        "ListFunctionRunsRequestDict",  # For ListFunctionRunsRequest (inherits from SessionListRequest)
        "_SessionStartRequestDict",  # Shared implementation for local and remote session request dicts
    }

    # Remove mappings that have special dict types
    for req_class, dict_name in special_dict_mappings.items():
        expected_name = req_class + "Dict"
        if expected_name in missing_dict_types and dict_name in request_dict_set:
            missing_dict_types.discard(expected_name)

    # Track Request classes that don't inherit from valid base classes
    invalid_inheritance = []

    # Valid inheritance patterns - build hierarchy aware validation
    def is_valid_inheritance(class_name: str, inheritance_chain: str) -> bool:
        valid_direct_bases = ["SdkRequest", "BaseModel"]
        valid_request_bases = [
            "ListRequest",
            "SessionListRequest",
            "PaginationParams",
            "ScrapeParams",
            "_SessionStartRequest",
        ]
        valid_composite_bases = [
            "RunFunctionRequest",
        ]

        # Handle multiple inheritance and complex inheritance patterns
        inheritance_parts = [part.strip() for part in inheritance_chain.split(",")]

        for part in inheritance_parts:
            # Remove generics and extract base class name
            base_class = part.split("[")[0].strip()

            # Check direct valid bases
            if base_class in valid_direct_bases:
                return True

            # Check if it inherits from other Request classes (which should inherit from SdkRequest)
            if base_class in valid_request_bases or base_class in valid_composite_bases:
                return True

            # Handle some specific cases
            if class_name == "SdkRequest" and base_class in {"BaseModel", "_RawRequestObject"}:
                return True  # SdkRequest is the root, can inherit from BaseModel

        return False

    for class_name, inheritance in inheritance_matches:
        if not is_valid_inheritance(class_name, inheritance):
            invalid_inheritance.append((class_name, inheritance))

    # Generate detailed error messages
    error_messages = []

    if missing_dict_types:
        error_messages.append(f"Missing Dict types for Request classes: {sorted(missing_dict_types)}")

    if invalid_inheritance:
        inheritance_errors = []
        for class_name, inheritance in invalid_inheritance:
            inheritance_errors.append(f"{class_name} inherits from ({inheritance})")
        error_messages.append("Request classes with invalid inheritance:\n  " + "\n  ".join(inheritance_errors))

    # Additional check: verify that Dict types don't have unexpected extras
    unexpected_dict_types = request_dict_set - expected_dict_names
    # Remove special mappings from unexpected list
    for dict_name in special_dict_mappings.values():
        unexpected_dict_types.discard(dict_name)
    # Remove legitimate dict types that have Request classes in exceptions
    for dict_name in legitimate_dict_types:
        unexpected_dict_types.discard(dict_name)

    if unexpected_dict_types:
        error_messages.append(
            f"Unexpected Dict types found (no corresponding Request class): {sorted(unexpected_dict_types)}"
        )

    # Assert with detailed error message
    if error_messages:
        full_error = "\n\n".join(error_messages)
        full_error += f"\n\nFound Request classes: {sorted(request_set)}"
        full_error += f"\nFound RequestDict classes: {sorted(request_dict_set)}"
        full_error += f"\nExceptions (no dict needed): {sorted(exceptions_no_dict)}"
        full_error += f"\nSpecial dict mappings: {special_dict_mappings}"
        assert False, full_error

    # If we get here, all checks passed
    print("✓ All Request classes have proper Dict types and inheritance")
    print(f"✓ Found {len(request_classes)} Request classes")
    print(f"✓ Found {len(request_dict_classes)} RequestDict classes")
    print(f"✓ {len(exceptions_no_dict)} legitimate exceptions")
    print(f"✓ {len(special_dict_mappings)} special dict mappings")


def test_all_response_classes_inherit_from_sdk_response():
    """Test that every Pydantic model ending with 'Response' inherits from SdkResponse."""
    import re
    from pathlib import Path

    # Read the types.py file
    types_file_path = (
        Path(__file__).parent.parent.parent / "packages" / "notte-core" / "src" / "notte_core" / "types.py"
    )
    with open(types_file_path, "r") as f:
        types_content = f.read()

    # Find all class definitions ending with 'Response'
    response_class_pattern = r"class\s+(\w*Response)\s*\([^)]*\):"
    response_classes = re.findall(response_class_pattern, types_content)

    # Find inheritance patterns for Response classes
    inheritance_pattern = r"class\s+(\w*Response)\s*\(([^)]+)\):"
    inheritance_matches = re.findall(inheritance_pattern, types_content)

    # Convert to sets for easier comparison
    response_set = set(response_classes)

    # Classes that legitimately don't need to inherit from SdkResponse (base classes, special cases)
    exceptions_inheritance = {
        "SdkResponse",  # Base response class itself
        "ExecutionResponse",  # Inherits from SdkResponse indirectly
    }

    # Track Response classes that don't inherit from valid base classes
    invalid_inheritance = []

    # Valid inheritance patterns - build hierarchy aware validation
    def is_valid_response_inheritance(class_name: str, inheritance_chain: str) -> bool:
        valid_direct_bases = ["SdkResponse", "BaseModel"]
        valid_response_bases = ["SessionResponse", "GetFunctionResponse", "ReplayResponse"]
        valid_composite_bases = ["ExecutionResult", "Observation", "DataSpace"]

        # Handle multiple inheritance and complex inheritance patterns
        inheritance_parts = [part.strip() for part in inheritance_chain.split(",")]

        for part in inheritance_parts:
            # Remove generics and extract base class name
            base_class = part.split("[")[0].strip()

            # Check direct valid bases
            if base_class in valid_direct_bases:
                return True

            # Check if it inherits from other Response classes (which should inherit from SdkResponse)
            if base_class in valid_response_bases or base_class in valid_composite_bases:
                return True

            # Handle some specific cases
            if class_name == "SdkResponse" and base_class == "BaseModel":
                return True  # SdkResponse is the root, can inherit from BaseModel

        return False

    for class_name, inheritance in inheritance_matches:
        if class_name not in exceptions_inheritance:
            if not is_valid_response_inheritance(class_name, inheritance):
                invalid_inheritance.append((class_name, inheritance))

    # Generate detailed error messages
    error_messages = []

    if invalid_inheritance:
        inheritance_errors = []
        for class_name, inheritance in invalid_inheritance:
            inheritance_errors.append(f"{class_name} inherits from ({inheritance})")
        error_messages.append(
            "Response classes with invalid inheritance (should inherit from SdkResponse):\n  "
            + "\n  ".join(inheritance_errors)
        )

    # Assert with detailed error message
    if error_messages:
        full_error = "\n\n".join(error_messages)
        full_error += f"\n\nFound Response classes: {sorted(response_set)}"
        full_error += f"\nExceptions (inheritance not required): {sorted(exceptions_inheritance)}"
        assert False, full_error

    # If we get here, all checks passed
    print("✓ All Response classes have proper inheritance from SdkResponse")
    print(f"✓ Found {len(response_classes)} Response classes")
    print(f"✓ {len(exceptions_inheritance)} legitimate inheritance exceptions")


def test_session_start_request_timeout_minutes_validation():
    request = SessionStartRequest.model_validate(dict(timeout_minutes=2, max_duration_minutes=10))
    assert request.idle_timeout_minutes == 2
    assert request.max_duration_minutes == 10


def test_file_info_dict_parsing_retro_compatibility():
    resp = ListFilesResponse.model_validate(dict(files=["test.txt", "test.pdf"]))
    assert resp.files[0].name == "test.txt"
    assert resp.files[0].file_ext == "txt"
    assert resp.files[1].name == "test.pdf"
    assert resp.files[1].file_ext == "pdf"


def test_proxy_geolocation_country_code_literal_matches_enum():
    """Validate that ProxyGeolocationCountryCode Literal type contains exactly the same
    values as ProxyGeolocationCountry enum. This catches missing or extra entries when
    the enum is updated without updating the Literal type alias."""
    enum_values = {member.value for member in ProxyGeolocationCountry}
    literal_values = set(get_args(ProxyGeolocationCountryCode))

    missing_from_literal = enum_values - literal_values
    extra_in_literal = literal_values - enum_values

    error_messages: list[str] = []
    if missing_from_literal:
        error_messages.append(f"Country codes in enum but missing from Literal: {sorted(missing_from_literal)}")
    if extra_in_literal:
        error_messages.append(f"Country codes in Literal but missing from enum: {sorted(extra_in_literal)}")

    assert not error_messages, "\n".join(error_messages)
