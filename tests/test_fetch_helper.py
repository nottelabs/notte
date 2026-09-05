"""`afetch()` runs the browser's `fetch()` inside the page and returns the response."""

import pytest
from notte_browser.session import NotteSession
from notte_core.errors.actions import ActionExecutionError


@pytest.mark.asyncio
async def test_afetch_resolves_a_relative_url_against_the_page() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://www.example.com/")

        response = await session.afetch("/")

        assert response.status_code == 200
        assert response.ok
        assert "Example Domain" in response.text
        assert response.url.startswith("https://www.example.com/")
        assert "content-type" in response.headers


@pytest.mark.asyncio
async def test_afetch_json_reads_the_body() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://www.example.com/")

        response = await session.afetch("data:application/json,%7B%22a%22%3A1%7D")

        assert response.json() == {"a": 1}


@pytest.mark.asyncio
async def test_afetch_network_failure_raises_the_js_error() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://www.example.com/")

        with pytest.raises(ActionExecutionError, match="JavaScript evaluation failed"):
            _ = await session.afetch("https://nonexistent.invalid/")


# NOTE: no sync-variant test here on purpose, for the same reason as
# test_evaluate_js_helper.py: a sync NotteSession in this process breaks the
# next async browser launch. The sync wrapper is a one-line delegation to afetch.
