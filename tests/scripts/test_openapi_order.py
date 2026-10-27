"""The Python and Node generators share an object-order policy, never an array sort."""

import json
from pathlib import Path

from scripts.openapi_order import comparison_json

FIXTURE = Path(__file__).parents[1] / "data/openapi-order"


def test_shared_ordering_fixture_and_idempotence() -> None:
    original = json.loads((FIXTURE / "input.json").read_text())
    expected = (FIXTURE / "expected.json").read_text()
    before = json.dumps(original)
    assert comparison_json(original) == expected
    assert json.dumps(original) == before
    assert comparison_json(json.loads(expected)) == expected
    reversed_objects = json.loads(expected, object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert comparison_json(reversed_objects) == expected
    # Object values and every array position are unchanged.
    assert json.loads(expected) == original


def test_real_values_are_not_normalized_away() -> None:
    original = json.loads((FIXTURE / "input.json").read_text())
    expected = comparison_json(original)
    original["components"]["schemas"]["Alpha"]["prefixItems"].reverse()
    assert comparison_json(original) != expected
    original["components"]["schemas"]["Alpha"]["prefixItems"].reverse()
    original["components"]["schemas"]["Alpha"]["examples"].reverse()
    assert comparison_json(original) != expected
