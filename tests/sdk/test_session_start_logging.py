"""Startup diagnostics keep the session identifier without recording client inputs."""

import json
from typing import Any

import pytest
from notte_core.logging import logger
from notte_sdk import NotteClient

from tests.sdk.test_generated_endpoints import fake
from tests.sdk.test_sessions_codegen import SESSION
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client


@pytest.mark.parametrize(
    "options, private_values",
    [
        (
            {
                "proxies": [
                    {
                        "type": "external",
                        "server": "https://fixture-user:fixture-url-secret@proxy.example.test:443",  # pragma: allowlist secret
                        "username": "fixture-proxy-user",
                        "password": "fixture-proxy-secret",  # pragma: allowlist secret
                    }
                ]
            },
            ["fixture-user", "fixture-url-secret", "fixture-proxy-user", "fixture-proxy-secret"],
        ),
        (
            {
                "proxies": [
                    {
                        "type": "tailnet",
                        "oauth_client_id": "fixture-oauth-client",
                        "oauth_client_secret": "fixture-oauth-secret",  # pragma: allowlist secret
                    }
                ]
            },
            ["fixture-oauth-client", "fixture-oauth-secret"],
        ),
        (
            {
                "cdp_url": "wss://browser.example.test/devtools/browser/fixture-browser?token=fixture-cdp-secret",  # pragma: allowlist secret
                "proxies": False,
            },
            ["fixture-browser", "fixture-cdp-secret"],
        ),
    ],
)
def test_session_start_keeps_private_inputs_on_wire_only(
    client: NotteClient,
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
    private_values: list[str],
) -> None:
    api = fake(monkeypatch, SESSION)
    records: list[str] = []
    handler = logger.add(lambda message: records.append(message.record["message"]), level="TRACE")
    try:
        session = client.Session(**options, wait_for_authentication=False)
        session.start(tries=1)
    finally:
        logger.remove(handler)
    wire = json.loads(api.calls[0].data)
    assert all(wire[key] == value for key, value in options.items())
    output = "\n".join(records)
    assert f"[Session] {SESSION['session_id']} started" in output
    for value in private_values:
        assert value not in output
