"""Serialize resource requests without duplicating the server's validation."""

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, RootModel, SecretStr, field_serializer


def _unmask(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, BaseModel):
        return _unmask(value.model_dump())
    if isinstance(value, dict):
        return {key: _unmask(item) for key, item in cast(dict[str, Any], value).items()}
    if isinstance(value, (list, tuple)):
        return [_unmask(item) for item in cast(list[Any] | tuple[Any, ...], value)]
    return value


class WireRequest(RootModel[dict[str, Any]]):
    @field_serializer("root")
    def serialize(self, value: dict[str, Any]) -> Any:
        return _unmask(value)


def wire_request(model: type[BaseModel] | None, data: Mapping[str, Any]) -> WireRequest:
    """Send caller fields only, preserving historical optional-null omission."""
    fields = model.model_fields if model is not None else {}
    return WireRequest(
        {
            key: value
            for key, value in data.items()
            if value is not None or key not in fields or fields[key].default is not None
        }
    )
