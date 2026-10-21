import pytest


@pytest.fixture(autouse=True)
def default_label_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests assume the default `NOTTE_ACT_LABELS` (accessible) unless they set it."""
    monkeypatch.delenv("NOTTE_ACT_LABELS", raising=False)
