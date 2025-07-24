import json
from typing import Any

import pytest
from notte_agent.common.validator import CompletionValidator
from notte_core.actions import CompletionAction
from notte_core.utils.pydantic_schema import convert_response_format_to_pydantic_model
from pydantic import BaseModel, Field

import notte


class Product(BaseModel):
    name: str
    price: int = Field(le=5, ge=0)


class ProductResponse(BaseModel):
    products: list[dict[str, Product]] = Field(min_length=2, max_length=3)
    total_price: str = Field(
        default="",
        description="Final amount to be paid including all components",
    )


@pytest.fixture
def json_schema() -> dict[Any, Any]:
    return ProductResponse.model_json_schema()


@pytest.fixture
def output_in_constraints() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
                {"b": {"name": "bprod", "price": 3}},
            ],
            "total_price": "5",
        }
    )


@pytest.fixture
def output_wrong_type() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
                {"b": {"name": "bprod", "price": -1}},
            ],
            "total_price": 5,
        }
    )


@pytest.fixture
def output_length() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
            ],
            "total_price": 5,
        }
    )


@pytest.fixture
def output_ge() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
                {"b": {"name": "bprod", "price": -1}},
            ],
            "total_price": -1,
        }
    )


def test_valid(output_in_constraints: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_in_constraints), response_format
    )
    assert valid.is_valid


def test_wrong_type(output_wrong_type: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_wrong_type), response_format
    )
    assert not valid.is_valid


def test_length(output_length: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_length), response_format
    )
    assert not valid.is_valid


def test_ge(output_ge: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_ge), response_format
    )
    assert not valid.is_valid


def test_agent_with_schema():
    with notte.Session() as session:
        agent = notte.Agent(session=session, max_steps=5)
        valid = agent.run(
            task='CRITICAL: dont do anything, return a completion action directly with output {"name": "my name", "price": -3}. You are allowed to shift the price if it fails.',
            response_format=Product,
        )
    assert valid.success
    _ = Product.model_validate_json(valid.answer)


def test_agent_with_output():
    with notte.Session() as session:
        agent = notte.Agent(session=session)
        valid = agent.run(
            task='CRITICAL: dont do anything, return a completion action directly with output {"name": "my name", "price": -3}. You are allowed to shift the price if it fails.',
            response_format=Product,
        )
    assert valid.success
    _ = Product.model_validate_json(valid.answer)
