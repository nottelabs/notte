"""Split a test run into CI shards: NOTTE_TEST_SHARD="<index>/<total>" (1-based)."""


def parse_shard(spec: str) -> tuple[int, int]:
    index, total = (int(part) for part in spec.split("/"))
    if not 1 <= index <= total:
        raise ValueError(f"Invalid NOTTE_TEST_SHARD={spec!r}")
    return index, total


def shard_nodeids(nodeids: list[str], spec: str) -> set[str]:
    """Keep every <total>-th test by sorted node id, so each shard gets a similar mix."""
    index, total = parse_shard(spec)
    return {nodeid for position, nodeid in enumerate(sorted(nodeids)) if position % total == index - 1}
