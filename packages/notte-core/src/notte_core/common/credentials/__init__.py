from __future__ import annotations

from typing import Any

from pydantic import SecretStr
from pydantic._internal import (
    _utils,
)
from pydantic.annotated_handlers import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from typing_extensions import override


class ValueWithPlaceholder(SecretStr):
    def __init__(self, secret_value: str, placeholder_value: str):
        super().__init__(secret_value)
        self.placeholder_value: str = placeholder_value

    @staticmethod
    def _serialize_secret_field(
        value: ValueWithPlaceholder, _: core_schema.SerializationInfo
    ) -> str | ValueWithPlaceholder:
        return value._display()

        # would rather differentiate it that way, so we don't lose the info
        # after a single dump, but it just doesnt work correctly for now
        # if info.mode == 'json':
        #     # we want the output to always be string without the `b'` prefix for bytes,
        #     # hence we just use `secret_display`
        #     return value._display()
        # else:
        #     return value

    @override
    def _display(self) -> str:
        return self.placeholder_value if self.get_secret_value() else ""

    @override
    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) and self.get_secret_value() == other.get_secret_value()

    @override
    def __hash__(self) -> int:
        return hash(self.get_secret_value())

    @override
    def __str__(self) -> str:
        return str(self._display())

    @override
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._display()!r})"

    @override
    @classmethod
    def __get_pydantic_core_schema__(cls, source: type[Any], handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        def get_json_schema(_core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
            json_schema = handler(cls._inner_schema)
            _utils.update_not_none(
                json_schema,
                type="string",
                writeOnly=True,
                format="password",
            )
            return json_schema

        def get_secret_schema(strict: bool) -> CoreSchema:
            inner_schema = {**cls._inner_schema, "strict": strict}
            json_schema = core_schema.no_info_after_validator_function(
                source,  # construct the type
                inner_schema,  # pyright: ignore[reportArgumentType]
            )
            return core_schema.json_or_python_schema(
                python_schema=core_schema.union_schema(
                    [
                        core_schema.is_instance_schema(source),
                        json_schema,
                    ],
                    custom_error_type=cls._error_kind,
                ),
                json_schema=json_schema,
                serialization=core_schema.plain_serializer_function_ser_schema(
                    ValueWithPlaceholder._serialize_secret_field,
                    info_arg=True,
                    when_used="always",
                ),
            )

        return core_schema.lax_or_strict_schema(
            lax_schema=get_secret_schema(strict=False),
            strict_schema=get_secret_schema(strict=True),
            metadata={"pydantic_js_functions": [get_json_schema]},
        )


def get_str_value(val: str | ValueWithPlaceholder) -> str:
    if isinstance(val, str):
        return val
    return val.get_secret_value()
