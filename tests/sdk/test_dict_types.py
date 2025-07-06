import os
from typing import Any, ClassVar, TypedDict, Union, get_args, get_origin, get_type_hints

import pytest
from dotenv import load_dotenv
from notte_core.common.config import NotteConfig, NotteConfigDict
from notte_core.llms.engine import LlmModel
from notte_sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    AgentCreateRequest,
    AgentCreateRequestDict,
    AgentListRequest,
    AgentListRequestDict,
    AgentRunRequest,
    AgentRunRequestDict,
    AgentStartRequest,
    AgentStatusRequest,
    AgentStatusRequestDict,
    CreatePhoneNumberRequest,
    CreatePhoneNumberRequestDict,
    DeleteCredentialsRequest,
    DeleteCredentialsRequestDict,
    DeleteCreditCardRequest,
    DeleteCreditCardRequestDict,
    DeleteVaultRequest,
    DeleteVaultRequestDict,
    GetCredentialsRequest,
    GetCredentialsRequestDict,
    GetCreditCardRequest,
    GetCreditCardRequestDict,
    ListCredentialsRequest,
    ListCredentialsRequestDict,
    MessageReadRequest,
    MessageReadRequestDict,
    PaginationParams,
    PaginationParamsDict,
    PersonaCreateRequest,
    PersonaCreateRequestDict,
    PersonaListRequest,
    PersonaListRequestDict,
    SdkAgentCreateRequest,
    SdkAgentCreateRequestDict,
    SessionListRequest,
    SessionListRequestDict,
    SessionResponse,
    SessionResponseDict,
    SessionStartRequest,
    SessionStartRequestDict,
    VaultCreateRequest,
    VaultCreateRequestDict,
    VaultListRequest,
    VaultListRequestDict,
)
from pydantic import BaseModel


def _test_request_dict_alignment(base_request: type[BaseModel], base_request_dict: type[TypedDict]) -> None:
    """Test that a BaseModel and its corresponding TypedDict have matching fields and types."""
    # Get all fields from BaseModel
    request_fields = get_type_hints(base_request)

    # Filter out ClassVar fields from BaseModel
    request_fields = {
        field_name: field_type
        for field_name, field_type in request_fields.items()
        if get_origin(field_type) is not ClassVar
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
        if get_origin(request_type) is Union:
            request_type_args = get_args(request_type)
            if type(None) in request_type_args:
                request_type = next(t for t in request_type_args if t is not type(None))

        if get_origin(dict_type) is Union:
            dict_type_args = get_args(dict_type)
            if type(None) in dict_type_args:
                dict_type = next(t for t in dict_type_args if t is not type(None))

        # Compare the types
        assert request_type == dict_type, (
            f"Type mismatch for field {field_name}: "
            f"{base_request.__name__} has {request_type} but {base_request_dict.__name__} has {dict_type}"
        )

    # Check that all fields in TypedDict are present in BaseModel
    for field_name in dict_fields:
        assert field_name in request_fields, (
            f"Field {field_name} from {base_request_dict.__name__} is missing in {base_request.__name__}"
        )


def test_agent_run_request_dict_alignment():
    _test_request_dict_alignment(AgentRunRequest, AgentRunRequestDict)


def test_agent_status_request_dict_alignment():
    _test_request_dict_alignment(AgentStatusRequest, AgentStatusRequestDict)


def test_session_start_request_dict_alignment():
    _test_request_dict_alignment(SessionStartRequest, SessionStartRequestDict)


def test_session_response_dict_alignment():
    _test_request_dict_alignment(SessionResponse, SessionResponseDict)


def test_session_list_request_dict_alignment():
    _test_request_dict_alignment(SessionListRequest, SessionListRequestDict)


def test_agent_list_request_dict_alignment():
    _test_request_dict_alignment(AgentListRequest, AgentListRequestDict)


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


def test_local_agent_create_request_dict_alignment():
    _test_request_dict_alignment(AgentCreateRequest, AgentCreateRequestDict)


def test_sdk_agent_create_request_dict_alignment():
    _test_request_dict_alignment(SdkAgentCreateRequest, SdkAgentCreateRequestDict)


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
    _test_request_dict_alignment(VaultListRequest, VaultListRequestDict)


def test_list_personas_request_dict_alignment():
    _test_request_dict_alignment(PersonaListRequest, PersonaListRequestDict)


def test_del_vault_request_dict_alignment():
    _test_request_dict_alignment(DeleteVaultRequest, DeleteVaultRequestDict)


def test_notte_config_dict_alignment():
    _test_request_dict_alignment(NotteConfig, NotteConfigDict)


def test_agent_run_request_default_values():
    """Test that AgentRunRequest has the correct default values."""
    request = AgentRunRequest(
        task="test_task",
        url="https://notte.cc",
    )

    assert request.task == "test_task"
    assert request.url == "https://notte.cc"


def test_agent_start_request_default_values():
    request = AgentStartRequest(
        task="test_task",
        session_id="test_session_id",
    )

    assert request.task == "test_task"
    assert request.reasoning_model == LlmModel.default()
    assert request.use_vision is True
    assert request.max_steps == DEFAULT_MAX_NB_STEPS
    assert request.vault_id is None
    assert request.session_id == "test_session_id"


@pytest.mark.parametrize("model", ["notavalid/gpt-4o-mini", "openrouter/google/gemma-3-27b-it"])
def test_agent_create_request_with_invalid_model(model: str):
    with pytest.raises(ValueError):
        _ = AgentCreateRequest(reasoning_model=model)


def test_agent_create_request_with_valid_model():
    _ = load_dotenv()
    if os.getenv("OPENAI_API_KEY") is None:
        with pytest.raises(ValueError):
            _ = AgentCreateRequest(reasoning_model="openai/gpt-4o")
    else:
        _ = AgentCreateRequest(reasoning_model="openai/gpt-4o")


@pytest.mark.parametrize(
    "params",
    [
        {"proxies": True},
        {"user_agent": "test"},
        {"chrome_args": ["test"]},
        {"viewport_width": 100},
        {"viewport_height": 100},
        {"solve_captchas": True},
    ],
)
def test_cannot_create_cdp_session_with_stealth_parameters(params: dict[str, Any]):
    with pytest.raises(ValueError):
        _ = SessionStartRequest(**params, cdp_url="test")


def test_should_be_able_to_start_cdp_session_with_default_session_parameters():
    _ = SessionStartRequest(cdp_url="test", headless=True)
