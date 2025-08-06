# Predefined schema templates as dict (ready for your converter)

import datetime as dt
from abc import ABCMeta, abstractmethod
from typing import Any

import pytest
from notte_core.utils.pydantic_schema import JsonResponseFormat, convert_response_format_to_pydantic_model
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import override


class _TestModel(BaseModel, metaclass=ABCMeta):
    @staticmethod
    @abstractmethod
    def example() -> "BaseModel":
        pass


class ShippingAddress(_TestModel):
    street_address: str
    name: str = Field(default="John", min_length=3, max_length=100, description="The name of the person")

    @override
    @staticmethod
    def example() -> "ShippingAddress":
        return ShippingAddress(street_address="730 Clayton St", name="Lucas")


class ProductResponse(_TestModel):
    item_name: str = Field(default="", description="Full product name with selected variants")
    price: float = Field(description="Original listing price before any discounts (in currency)")
    variants: list[str] = Field(default_factory=list, description="list of chosen options (color, size, etc.)")
    quantity: int | None = Field(default=1, description="Number of items in cart.", le=10, ge=1)
    address: ShippingAddress = Field(default_factory=ShippingAddress.example)

    @override
    @staticmethod
    def example() -> "ProductResponse":
        return ProductResponse(
            item_name="Product Name",
            price=100.0,
            variants=["Red", "Large"],
            quantity=2,
            address=ShippingAddress.example(),
        )


class PricingPlan(_TestModel):
    name: str
    trial_period_days: int | None
    is_popular: bool
    features: dict[str, str]

    @override
    @staticmethod
    def example() -> "PricingPlan":
        return PricingPlan(name="Free", trial_period_days=0, is_popular=False, features={"test": "test"})


class PricingPlans(_TestModel):
    plans: list[PricingPlan]
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())

    @override
    @staticmethod
    def example() -> "PricingPlans":
        return PricingPlans(plans=[PricingPlan.example()])


@pytest.mark.parametrize(
    "model",
    [
        PricingPlans,
        PricingPlan,
        ProductResponse,
        ShippingAddress,
    ],
)
def test_pydantic_schema(model: type[_TestModel]):
    try:
        schema = JsonResponseFormat.model_validate(model.model_json_schema())
    except ValidationError as e:
        raise ValueError(f"Error validating schema for {model.model_json_schema()}: {e}") from e
    schema_dict = schema.model_dump()
    assert schema_dict == model.model_json_schema()
    ResponseFormat = convert_response_format_to_pydantic_model(schema_dict)
    assert ResponseFormat is not None
    example = model.example()
    # try to create an instance of the model with the example
    instance = ResponseFormat.model_validate(example.model_dump())
    assert instance is not None
    assert instance.model_dump() == example.model_dump()


@pytest.fixture
def json_response_format():
    return {
        "type": "object",
        "properties": {
            "pricing_plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "price": {"type": "string"},
                        "billing_period": {"type": "string"},
                        "features": {"type": "array", "items": {"type": "string"}},
                        "cta_text": {"type": "string"},
                    },
                },
            }
        },
        "required": ["pricing_plans"],
    }


def test_json_response_format_conversion(json_response_format: dict[str, Any]):
    Format = convert_response_format_to_pydantic_model(json_response_format)
    assert Format is not None
    assert Format.model_json_schema() == json_response_format
