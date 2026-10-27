"""The Python and Node generators share an object-order policy, never an array sort."""

import json
from pathlib import Path

from scripts.openapi_order import serialize_openapi

FIXTURE = Path(__file__).parents[1] / "data/openapi-order"


def test_shared_ordering_fixture_and_idempotence() -> None:
    original = json.loads((FIXTURE / "input.json").read_text())
    expected = (FIXTURE / "expected.json").read_text()
    assert serialize_openapi(original) == expected
    assert serialize_openapi(json.loads(expected)) == expected
    reversed_objects = json.loads(expected, object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert serialize_openapi(reversed_objects) == expected
    # Object values and every array position are unchanged.
    assert json.loads(expected) == original


def test_real_values_are_not_normalized_away() -> None:
    original = json.loads((FIXTURE / "input.json").read_text())
    expected = serialize_openapi(original)
    original["components"]["schemas"]["Alpha"]["prefixItems"].reverse()
    assert serialize_openapi(original) != expected
    original["components"]["schemas"]["Alpha"]["prefixItems"].reverse()
    original["components"]["schemas"]["Alpha"]["examples"].reverse()
    assert serialize_openapi(original) != expected
