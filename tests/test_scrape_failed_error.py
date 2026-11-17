import pytest
from notte_core.data import StructuredData
from notte_core.errors import ErrorConfig, ErrorMode, ScrapeFailedError
from pydantic import BaseModel


@pytest.mark.parametrize("mode", ["developer", "agent"])
def test_scrape_failed_error_says_attributes_are_not_extracted(mode: ErrorMode) -> None:
    with ErrorConfig.message_mode(mode):
        message = str(ScrapeFailedError("no rating found"))
    assert "no rating found" in message
    assert "drops other HTML attributes" in message
    assert "aria-label" in message
    assert "session.evaluate_js(" in message


def test_failed_structured_data_raises_with_attribute_hint() -> None:
    failed = StructuredData[BaseModel](success=False, error="no rating found", data=None)
    with pytest.raises(ScrapeFailedError, match="drops other HTML attributes"):
        _ = failed.get()
