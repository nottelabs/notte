import pytest

from tests.ci_shard import parse_shard, shard_nodeids

NODEIDS = [f"tests/integration/test_{name}.py::test_{i}" for name in ("agent", "vault", "scrape") for i in range(7)]


@pytest.mark.parametrize("total", [1, 2, 3, 4, 7])
def test_shards_partition_every_test_exactly_once(total: int) -> None:
    shards = [shard_nodeids(NODEIDS, f"{index}/{total}") for index in range(1, total + 1)]
    assert set().union(*shards) == set(NODEIDS)
    assert sum(len(shard) for shard in shards) == len(NODEIDS)
    assert max(len(shard) for shard in shards) - min(len(shard) for shard in shards) <= 1


def test_shard_selection_ignores_collection_order() -> None:
    assert shard_nodeids(NODEIDS, "2/4") == shard_nodeids(list(reversed(NODEIDS)), "2/4")


def test_tests_from_one_file_are_spread_across_shards() -> None:
    agent_tests = [nodeid for nodeid in NODEIDS if "test_agent.py" in nodeid]
    for index in range(1, 5):
        assert len(shard_nodeids(agent_tests, f"{index}/4")) <= 2


@pytest.mark.parametrize("spec", ["0/4", "5/4", "1/0", "x/4", "4"])
def test_invalid_shard_specs_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError):
        _ = parse_shard(spec)
