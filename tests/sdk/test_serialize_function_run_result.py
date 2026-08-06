import json

from notte_sdk.utils import serialize_function_run_result
from pydantic import BaseModel


class _UseCase(BaseModel):
    id: str
    slug: str


class _Catalog(BaseModel):
    use_cases: list[_UseCase]


def test_serialize_pydantic_model_as_json() -> None:
    result = _Catalog(use_cases=[_UseCase(id="1", slug="hipcamp")])

    serialized = serialize_function_run_result(result)

    assert json.loads(serialized) == {
        "use_cases": [{"id": "1", "slug": "hipcamp"}],
    }
    assert "UseCase(" not in serialized


def test_serialize_list_of_pydantic_models_as_json() -> None:
    result = [_UseCase(id="1", slug="a"), _UseCase(id="2", slug="b")]

    serialized = serialize_function_run_result(result)

    assert json.loads(serialized) == [
        {"id": "1", "slug": "a"},
        {"id": "2", "slug": "b"},
    ]


def test_serialize_plain_dict_and_str_unchanged_shape() -> None:
    assert json.loads(serialize_function_run_result({"a": 1})) == {"a": 1}
    assert serialize_function_run_result("already a string") == "already a string"


def test_serialize_non_json_object_falls_back_to_str() -> None:
    class _Opaque:
        def __str__(self) -> str:
            return "opaque-value"

    assert serialize_function_run_result(_Opaque()) == "opaque-value"
