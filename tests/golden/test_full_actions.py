"""Supplement the existing saved-page snapshots without changing their files."""

from pathlib import Path

import pytest

from tests.characterization.snapshots import capture_observations, check_snapshot
from tests.golden.test_golden_pages import PAGES, SNAPSHOTS_DIR


@pytest.mark.parametrize("page", PAGES, ids=str)
def test_full_actions(page: Path, tmp_path: Path) -> None:
    _, actions = capture_observations(page.as_posix(), tmp_path / "actual.json", saved_page=True)
    check_snapshot(SNAPSHOTS_DIR / page.with_suffix("") / "actions.json", actions)
