"""`generate_llms.py` reuses the committed API section unless asked to refresh it.

The pre-commit hook regenerates llms.txt on every run, so the default path must
not depend on the live OpenAPI spec: any drift in the API between a local run and
CI would otherwise fail the hook on unrelated pull requests.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "docs" / "src" / "scripts" / "generate_llms.py"
URL = "https://api.example.test/openapi.json"


@pytest.fixture(scope="module")
def generate_llms() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_llms", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def existing_llms(generate_llms: ModuleType) -> str:
    return "\n".join(
        [
            "## APIs",
            "",
            generate_llms.openapi_begin_marker(URL),
            "",
            "## Sessions",
            "",
            "- [POST Session Start](https://docs.notte.cc/api-reference/sessions/session-start.md)",
            "",
            generate_llms.OPENAPI_END_MARKER,
            "",
            "## SDK",
        ]
    )


def test_default_run_reuses_the_committed_section_without_fetching(
    generate_llms: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(url: str) -> dict:
        raise AssertionError(f"fetched {url} in offline mode")

    monkeypatch.setattr(generate_llms, "fetch_openapi", no_network)

    section = generate_llms.openapi_section(URL, refresh=False, existing=existing_llms(generate_llms))

    assert section[0] == generate_llms.openapi_begin_marker(URL)
    assert "- [POST Session Start](https://docs.notte.cc/api-reference/sessions/session-start.md)" in section
    assert section[-2] == generate_llms.OPENAPI_END_MARKER


def test_refresh_rebuilds_the_section_from_the_live_spec(
    generate_llms: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = {
        "paths": {
            "/sessions/start": {
                "post": {"tags": ["sessions"], "summary": "Session Start", "operationId": "session_start"}
            }
        }
    }
    monkeypatch.setattr(generate_llms, "fetch_openapi", lambda url: spec)

    section = generate_llms.openapi_section(URL, refresh=True, existing="stale text without markers")

    assert section[0] == generate_llms.openapi_begin_marker(URL)
    assert "- [POST Session Start](https://docs.notte.cc/api-reference/sessions/session-start.md)" in section
    assert generate_llms.OPENAPI_END_MARKER in section


def test_missing_cached_section_falls_back_to_fetching(
    generate_llms: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        return {"paths": {}}

    monkeypatch.setattr(generate_llms, "fetch_openapi", fetch)

    section = generate_llms.openapi_section(URL, refresh=False, existing="no markers here")

    assert calls == [URL]
    assert section[0] == generate_llms.openapi_begin_marker(URL)


def test_failed_fetch_keeps_the_stub_line_for_the_refresh_workflow(
    generate_llms: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fetch(url: str) -> dict:
        raise OSError("offline")

    monkeypatch.setattr(generate_llms, "fetch_openapi", fetch)

    section = generate_llms.openapi_section(URL, refresh=True, existing="")

    # refresh-llms.yml greps stderr for this phrase to refuse a degraded file
    assert "failed to fetch openapi" in capsys.readouterr().err
    assert section == [f"- OpenAPI spec: {URL}", ""]
