from typing import Iterator

import pytest

from tests.browser.referrences.observe_utils import (
    start_local_html_server,
    verify_data_snapshots,
)


@pytest.fixture(scope="session")
def local_html_server() -> Iterator[str]:  # pragma: no cover
    with start_local_html_server() as url:
        yield url


def test_observe_snapshot(local_html_server: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""

    verify_data_snapshots(local_html_server)
