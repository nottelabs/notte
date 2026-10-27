"""Local extraction across pinned upstreams; run with -n 6 --dist loadgroup -rA.

Each upstream's four cases stay on one worker to avoid bursts against that pin.
The CI job publishes JUnit properties and a per-route summary, including downgrades.
"""

import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from notte_core.data import StructuredData
from notte_llm import LlmExtractor
from pydantic import BaseModel

from tests.llm.provider_matrix import (
    CASES,
    EXPECTED_LINKS,
    EXTRACTION_INSTRUCTIONS,
    ROUTES,
    Route,
    Trace,
    UnavailableRoute,
    routing_options,
)

pytestmark = [pytest.mark.live, pytest.mark.asyncio]
SNAPSHOTS = Path(__file__).parents[1] / "golden" / "snapshots"


class Link(BaseModel):
    label: str
    url: str
    description: str | None = None


class Page(BaseModel):
    title: str
    links: list[Link]
    summary: str | None = None


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    "route", [pytest.param(route, id=route.name, marks=pytest.mark.xdist_group(route.name)) for route in ROUTES]
)
async def test_provider_matrix(route: Route, case: str, monkeypatch: pytest.MonkeyPatch, record_property: Any) -> None:
    record_property("route", route.name)
    record_property("model", route.model)
    record_property("upstream", route.upstream or "Vertex direct")
    record_property("case", case)
    trace = Trace()
    start = time.perf_counter()
    try:
        # Every route gets a fresh endpoint configuration; local .env overrides cannot
        # accidentally send a CI key to another endpoint or turn this into a cloud test.
        for name in ("NOTTE_LLM_BASE_URL", "NOTTE_LLM_API_KEY", "NOTTE_LLM_MODEL"):
            monkeypatch.delenv(name, raising=False)
        if route.name == "vertex":
            key = os.getenv("NOTTE_VERTEX_API_KEY", "")
            base = os.getenv("NOTTE_VERTEX_BASE_URL", "")
            if not key or not base:
                pytest.skip("Vertex credentials absent; configure_llm.py mints the optional direct-route token")
            monkeypatch.setenv("NOTTE_LLM_BASE_URL", base)
            monkeypatch.setenv("NOTTE_LLM_API_KEY", key)
            model, options = os.getenv("NOTTE_VERTEX_MODEL") or route.model, {}
        else:
            key = os.getenv("OPENROUTER_API_KEY", "")
            if not key:
                pytest.skip("OPENROUTER_API_KEY absent; fork/external PRs have no repository secrets")
            try:
                model, options = routing_options(route)
            except UnavailableRoute as error:
                pytest.skip(str(error))
        record_property("resolved_model", model)
        record_property("max_completion_tokens", options.get("max_completion_tokens", 8192))
        original_send = httpx.AsyncClient.send

        async def send(client: httpx.AsyncClient, request: httpx.Request, **kwargs: Any) -> httpx.Response:
            attempt = trace.observe(request)
            try:
                response = await original_send(client, request, **kwargs)
            except httpx.TimeoutException as error:
                attempt.error = type(error).__name__
                raise
            trace.response(attempt, response, key)
            return response

        monkeypatch.setattr(httpx.AsyncClient, "send", send)
        document_case = "github_signin" if case == "instructions" else case
        result = await LlmExtractor(model=model).extract(
            url="https://example.com",
            document=(SNAPSHOTS / document_case / "scrape.md").read_text(),
            response_format=None if case == "instructions" else Page,
            instructions=EXTRACTION_INSTRUCTIONS,
            extra_body=options,
        )
        assert result.success, result.error
        assert result.data is not None
        if case == "instructions":
            validated = StructuredData.model_validate(result.model_dump())
            assert validated.success and validated.data is not None
            assert isinstance(result.data.model_dump(), dict) and result.data.model_dump()
        else:
            page = Page.model_validate(result.data.model_dump(), strict=True)
            assert page.title
            assert tuple((link.label, link.url) for link in page.links) == EXPECTED_LINKS[document_case]
    except Exception as error:
        reason = trace.capacity_reason(error)
        if reason:
            pytest.skip(reason)
        raise
    finally:
        path = " → ".join(attempt.path for attempt in trace.attempts)
        record_property("format_path", path or "not requested")
        record_property("latency_seconds", round(time.perf_counter() - start, 3))
        record_property("providers", ", ".join(sorted({a.provider for a in trace.attempts if a.provider})))
        print(f"PROVIDER_MATRIX {route.name}/{case}: {path or 'not requested'}", flush=True)
