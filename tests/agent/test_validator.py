import json
from typing import Any

import pytest
from notte_agent.common.validator import CompletionValidator
from notte_core.actions import CompletionAction
from pydantic import BaseModel, Field

from notte import Agent


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
    valid = CompletionValidator.validate_json_output(
        CompletionAction(success=True, answer=output_in_constraints), json_schema
    )
    assert valid.is_valid


def test_wrong_type(output_wrong_type: str, json_schema: dict[Any, Any]):
    valid = CompletionValidator.validate_json_output(
        CompletionAction(success=True, answer=output_wrong_type), json_schema
    )
    assert not valid.is_valid


def test_length(output_length: str, json_schema: dict[Any, Any]):
    valid = CompletionValidator.validate_json_output(CompletionAction(success=True, answer=output_length), json_schema)
    assert not valid.is_valid


def test_ge(output_ge: str, json_schema: dict[Any, Any]):
    valid = CompletionValidator.validate_json_output(CompletionAction(success=True, answer=output_ge), json_schema)
    assert not valid.is_valid


def test_agent_with_schema():
    agent = Agent()
    valid = agent.run(
        task='CRITICAL: dont do anything, return a completion action directly with output {"name": "my name", "price": -3}. You are allowed to shift the price if it fails.',
        output_schema=Product.model_json_schema(),
    )
    assert valid.success
    _ = Product.model_validate_json(valid.answer)


def test_agent_with_output():
    agent = Agent()
    valid = agent.run(
        task='CRITICAL: dont do anything, return a completion action directly with output {"name": "my name", "price": -3}. You are allowed to shift the price if it fails.',
        output_model=Product,
    )
    assert valid.success
    _ = Product.model_validate_json(valid.answer)
