"""AacVault against the real `aac` CLI (installed at a pinned version in CI) and the public aac proxy.

Handing out a credential needs a user running `aac listen`, which only runs in a terminal. These tests
cover what the CLI answers without one: it accepts the flags AacVault passes and its JSON errors parse.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from notte_core.credentials.aac import AacVault, _AacResponse  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.skipif(shutil.which("aac") is None, reason="aac CLI not installed")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # aac caches its identity and connections under $HOME
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AAC_TOKEN", raising=False)


@pytest.fixture()
def aac_results(monkeypatch: pytest.MonkeyPatch) -> list[subprocess.CompletedProcess[str]]:
    """The completed `aac` processes AacVault ran."""
    results: list[subprocess.CompletedProcess[str]] = []
    run = subprocess.run

    def recording_run(
        cmd: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool, env: dict[str, str] | None
    ) -> subprocess.CompletedProcess[str]:
        result = run(cmd, capture_output=capture_output, text=text, timeout=timeout, check=check, env=env)
        results.append(result)
        return result

    monkeypatch.setattr(subprocess, "run", recording_run)
    return results


def _error_message(result: subprocess.CompletedProcess[str]) -> str:
    response = _AacResponse.model_validate_json(result.stdout)
    assert not response.success
    assert response.error is not None
    return response.error.message


def test_without_a_connection_returns_none(aac_results: list[subprocess.CompletedProcess[str]]) -> None:
    with AacVault(timeout=5) as vault:
        assert vault.get_credentials("https://example.com") is None

    [result] = aac_results
    assert "No cached connections" in _error_message(result)


def test_invalid_token_returns_none_and_keeps_the_token(aac_results: list[subprocess.CompletedProcess[str]]) -> None:
    with AacVault(token="INVALID99", timeout=5) as vault:
        assert vault.get_credentials("https://example.com") is None
        assert vault.token == "INVALID99"

    [result] = aac_results
    assert "Pairing failed" in _error_message(result)
