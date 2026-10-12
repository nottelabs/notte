"""Image scraping (`scrape(only_images=True)`) was removed in v2, but the cloud API (notte 1.x) still
returns `images` in scrape responses and records `only_images` on scrape steps. v2 models must keep
parsing those payloads: the legacy keys are ignored, not rejected."""

from notte_core.actions import ScrapeAction
from notte_core.browser.observation import ExecutionResult
from notte_core.data.space import DataSpace
from notte_core.types import ScrapeResponse


def test_scrape_response_with_legacy_images_key_parses() -> None:
    for images in (None, [], [{"url": "https://example.com/logo.png", "category": "icon", "description": None}]):
        payload = {"markdown": "# Title", "images": images, "structured": None}

        data = ScrapeResponse.model_validate(payload)

        assert isinstance(data, DataSpace)
        assert data.markdown == "# Title"
        assert data.structured is None
        assert "images" not in data.model_dump()


def test_recorded_scrape_action_with_legacy_only_images_parses() -> None:
    for only_images in (False, True):
        action = ScrapeAction.model_validate({"type": "scrape", "only_main_content": True, "only_images": only_images})

        assert action.only_main_content is True
        assert "only_images" not in action.model_dump()


def test_recorded_scrape_step_from_legacy_api_parses() -> None:
    payload = {
        "action": {"type": "scrape", "instructions": None, "only_images": True, "scrape_links": True},
        "success": True,
        "message": "Scraped images from the current page",
        "data": {"markdown": "", "images": [{"url": "https://example.com/logo.png", "category": "favicon"}]},
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:01Z",
    }

    result = ExecutionResult.model_validate(payload)

    assert isinstance(result.action, ScrapeAction)
    assert result.data is not None and result.data.markdown == ""
