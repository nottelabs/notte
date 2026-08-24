"""
Collection-typed variables arriving as strings.

A caller that sends `keywords="['a', 'b']"` for `keywords: list[str]` hands the
script a string where it expects two items. Every client hits it, because the
ones that build a payload from a stored default are echoing back the Python
source `ast.unparse` wrote when the parameter was recorded.
"""

import pytest
from notte_core.ast import ParameterInfo, coerce_collection_variables


def coerce(annotation: str | None, value: object) -> object:
    variables: dict[str, object] = {"x": value}
    coerce_collection_variables([ParameterInfo(name="x", type=annotation)], variables)
    return variables["x"]


@pytest.mark.parametrize(
    "annotation",
    [
        "list[str]",
        "list",
        "Optional[list[str]]",
        "list[str] | None",
        "typing.List[str]",
        "Sequence[str]",
        "Annotated[list[str], Field(description='x')]",
        "Union[list[str], str]",
        "tuple[str, str]",
        "set[str]",
    ],
)
def test_reads_a_python_literal_for_every_sequence_spelling(annotation: str) -> None:
    # `ast.unparse` produces all of these, and a parameter that has a default is
    # very often wrapped in `Optional[...]`.
    assert coerce(annotation, "['a', 'b']") == ["a", "b"]


@pytest.mark.parametrize("annotation", ["dict[str, int]", "Optional[dict[str, Any]]", "Mapping[str, int]"])
def test_reads_a_mapping(annotation: str) -> None:
    assert coerce(annotation, "{'a': 1}") == {"a": 1}


def test_reads_json_too() -> None:
    # What an HTTP caller sends, as opposed to what a stored default looks like.
    assert coerce("list[str]", '["a", "b"]') == ["a", "b"]
    assert coerce("dict[str, int]", '{"a": 1}') == {"a": 1}


def test_the_outermost_container_decides() -> None:
    # `dict[str, list[str]]` is a mapping, not a sequence that mentions one.
    # Handing a dict parameter a list would be a silently wrong argument.
    assert coerce("dict[str, list[str]]", "['a', 'b']") == "['a', 'b']"
    assert coerce("list[str]", "{'a': 1}") == "{'a': 1}"
    assert coerce("dict[str, list[str]]", "{'a': ['x']}") == {"a": ["x"]}


@pytest.mark.parametrize(
    "annotation,value",
    [
        ("str", "['a', 'b']"),
        ("int", "20"),
        ("bool", "true"),
        ("Any", "123"),
        (None, "['a']"),
    ],
)
def test_leaves_everything_that_is_not_a_collection_alone(annotation: str | None, value: str) -> None:
    # Load-bearing. Across a fortnight of production runs, int and bool
    # parameters received strings and succeeded 5,166 times: Python is
    # duck-typed and the scripts cope. Coercing those would break working calls.
    assert coerce(annotation, value) == value


def test_leaves_a_value_that_is_already_structured() -> None:
    assert coerce("list[str]", ["a"]) == ["a"]
    assert coerce("dict[str, int]", {"a": 1}) == {"a": 1}


def test_passes_through_anything_it_cannot_read() -> None:
    # No worse than the behaviour this replaces, and never an exception.
    for value in ("not a literal", "['unterminated", "DEFAULT_KEYWORDS", "list()"):
        assert coerce("list[str]", value) == value


def test_evaluates_no_names_and_no_calls() -> None:
    # literal_eval, not eval: a name or a call raises rather than resolving.
    assert coerce("list[str]", "__import__('os').listdir()") == "__import__('os').listdir()"


def test_empty_set_source_becomes_an_empty_list() -> None:
    # CPython special-cases `set()` in literal_eval because there is no
    # empty-set literal, so this evaluates rather than raising. `[]` is the
    # value the parameter asked for, and better than four characters of source.
    assert coerce("set[str]", "set()") == []


def test_a_singleton_tuple_keeps_its_element() -> None:
    # `ast.unparse` writes every 1-tuple with a trailing comma.
    assert coerce("tuple[str]", "('a',)") == ["a"]


def test_absent_and_empty_variables_are_safe() -> None:
    assert coerce_collection_variables([], {}) == {}
    variables: dict[str, object] = {"x": "['a']"}
    # A variable with no matching parameter is not coerced or dropped.
    assert coerce_collection_variables([ParameterInfo(name="other", type="list[str]")], variables) == {"x": "['a']"}


@pytest.mark.parametrize(
    "annotation",
    [
        "'list[str]'",
        '"list[str]"',
        "Optional['list[str]']",
        "'Optional[list[str]]'",
    ],
)
def test_quoted_annotations_are_read_through(annotation: str) -> None:
    # `def f(x: "list[str]")` is a forward reference, and `ast.unparse` records
    # it with the quotes still on. Reading it as a plain constant would skip
    # coercion and hand the script the raw string, which is the silent wrong
    # answer this module exists to prevent.
    assert coerce(annotation, '["a", "b"]') == ["a", "b"]


def test_a_quoted_scalar_is_still_not_a_collection() -> None:
    # Unwrapping the quotes must not turn every quoted annotation into one.
    assert coerce("'int'", "5") == "5"
    assert coerce("'NotAType'", "['a']") == "['a']"


def test_a_quoted_annotation_that_is_not_a_type_is_ignored() -> None:
    # The inner text does not have to parse. It must not raise if it does not.
    assert coerce("'['", "['a']") == "['a']"


def test_deeply_nested_json_does_not_end_the_run() -> None:
    # `json.loads` recurses per nesting level and raises RecursionError rather
    # than rejecting the text. Declining the value passes the original string
    # through; letting the error escape would kill the run instead.
    deep = "[" * 60_000 + "]" * 60_000
    assert coerce("list[str]", deep) == deep


def test_a_huge_flat_json_document_does_not_end_the_run() -> None:
    # The other half of the same rule: a parser may fail on the size or shape of
    # the input rather than its syntax, and neither way is worth a dead run.
    assert coerce("list[str]", "[" + "0," * 200_000 + "0]") is not None
