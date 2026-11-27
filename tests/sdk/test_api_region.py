"""The API host follows the credential's data region unless a URL is configured."""

from collections.abc import Iterator

import pytest
from notte_core.logging import logger
from notte_sdk import AsyncNotteClient, NotteClient, auth
from notte_sdk.auth import DEFAULT_API_URL, EU_API_URL, default_api_url
from notte_sdk.endpoints.base import BaseClient

from tests.sdk.test_generated_endpoints import PROFILE, fake

EU_KEYS = [
    "sk-notte-eu-0123456789abcdef",  # pragma: allowlist secret
    "sk-notte-org-eu-0123456789abcdef",  # pragma: allowlist secret
    "nat_eu_0123456789abcdef",  # pragma: allowlist secret
]
DEFAULT_KEYS = [
    "sk-notte-0123456789abcdef",  # pragma: allowlist secret
    "sk-notte-org-0123456789abcdef",  # pragma: allowlist secret
    "nat_0123456789abcdef",  # pragma: allowlist secret
    "sk-notte-europe0123456789",  # pragma: allowlist secret
    "sk-notte-org-europe0123456789",  # pragma: allowlist secret
    "nat_europe_0123456789",  # pragma: allowlist secret
    "nat_eu0123456789",  # pragma: allowlist secret
    "sk-notte-us-eu-0123456789",  # pragma: allowlist secret
    "SK-NOTTE-EU-0123456789",  # pragma: allowlist secret
    "test-api-key",  # pragma: allowlist secret
]


@pytest.fixture(autouse=True)
def no_configured_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTTE_API_URL", raising=False)
    monkeypatch.delenv("NOTTE_API_KEY", raising=False)
    monkeypatch.setattr(BaseClient, "check_and_warn_version_mismatch", lambda _: None)


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    try:
        yield messages
    finally:
        logger.remove(sink)


def _url_warnings(messages: list[str]) -> list[str]:
    return [message for message in messages if "NOTTE_API_URL is set to" in message]


def test_default_url_constant_is_unchanged() -> None:
    assert BaseClient.DEFAULT_NOTTE_API_URL == DEFAULT_API_URL == "https://api.notte.cc"
    assert EU_API_URL == "https://eu-api.notte.cc"


@pytest.mark.parametrize("key", EU_KEYS)
def test_eu_credentials_default_to_the_eu_api(key: str) -> None:
    assert default_api_url(key) == EU_API_URL


@pytest.mark.parametrize("key", [*DEFAULT_KEYS, None])
def test_other_credentials_default_to_the_default_api(key: str | None) -> None:
    assert default_api_url(key) == DEFAULT_API_URL


@pytest.mark.parametrize("key", EU_KEYS)
def test_an_eu_key_sends_every_client_to_the_eu_api(key: str, warnings: list[str]) -> None:
    client = NotteClient(api_key=key)
    resources: list[BaseClient] = [
        client.sessions,
        client.personas,
        client.vaults,
        client.profiles,
        client.managed_auth,
        client.files,
        client.functions,
    ]
    assert {resource.server_url for resource in resources} == {EU_API_URL}
    assert not client.sessions.is_custom_endpoint_available()
    assert _url_warnings(warnings) == []


@pytest.mark.parametrize("key", DEFAULT_KEYS)
def test_an_unmarked_key_keeps_the_default_api(key: str, warnings: list[str]) -> None:
    client = NotteClient(api_key=key)
    assert client.sessions.server_url == client.functions.server_url == DEFAULT_API_URL
    assert _url_warnings(warnings) == []


def test_an_eu_key_from_the_environment_selects_the_eu_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_API_KEY", EU_KEYS[1])
    assert NotteClient().sessions.server_url == EU_API_URL


def test_an_eu_key_from_the_cli_keyring_selects_the_eu_api(monkeypatch: pytest.MonkeyPatch) -> None:
    looked_up: list[str] = []

    def keyring(api_url: str) -> str:
        looked_up.append(api_url)
        return EU_KEYS[0]

    monkeypatch.setattr(auth, "get_keyring_api_key", keyring)
    client = NotteClient()
    assert client.sessions.token == EU_KEYS[0]
    assert client.sessions.server_url == EU_API_URL
    # The keyring is still read for the default API's environment.
    assert set(looked_up) == {DEFAULT_API_URL}


@pytest.mark.parametrize("key", [EU_KEYS[0], DEFAULT_KEYS[0]])
def test_an_explicit_server_url_wins(key: str, warnings: list[str]) -> None:
    client = NotteClient(api_key=key, server_url="https://custom.example")
    assert client.sessions.server_url == client.functions.server_url == "https://custom.example"
    assert _url_warnings(warnings) != []


@pytest.mark.parametrize("key", [EU_KEYS[0], DEFAULT_KEYS[0]])
def test_notte_api_url_wins(key: str, monkeypatch: pytest.MonkeyPatch, warnings: list[str]) -> None:
    monkeypatch.setenv("NOTTE_API_URL", "https://us-staging.notte.cc")
    client = NotteClient(api_key=key)
    assert client.sessions.server_url == client.functions.server_url == "https://us-staging.notte.cc"
    assert _url_warnings(warnings) != []


def test_an_eu_key_pointed_at_the_default_api_still_warns(warnings: list[str]) -> None:
    client = NotteClient(api_key=EU_KEYS[0], server_url=DEFAULT_API_URL)
    assert client.sessions.server_url == DEFAULT_API_URL
    assert _url_warnings(warnings) != []


def test_requests_with_an_eu_key_reach_the_eu_api(monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, PROFILE)
    client = NotteClient(api_key=EU_KEYS[0])
    _ = client.profiles.create()
    assert [request.url.host for request in api.requests] == ["eu-api.notte.cc"]


def test_a_resource_client_built_alone_follows_the_key() -> None:
    from notte_sdk.endpoints.sessions import SessionsClient

    client = NotteClient(api_key=EU_KEYS[0])
    assert SessionsClient(root_client=client, api_key=EU_KEYS[0]).server_url == EU_API_URL


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "expected"), [(EU_KEYS[2], EU_API_URL), (DEFAULT_KEYS[0], DEFAULT_API_URL)])
async def test_the_async_client_follows_the_key(key: str, expected: str, warnings: list[str]) -> None:
    async with AsyncNotteClient(api_key=key) as client:
        assert client.sessions.server_url == client.functions.server_url == client.profiles.server_url == expected
    assert _url_warnings(warnings) == []


@pytest.mark.asyncio
async def test_the_async_client_honors_notte_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_API_URL", "https://us-staging.notte.cc")
    async with AsyncNotteClient(api_key=EU_KEYS[0]) as client:
        assert client.sessions.server_url == "https://us-staging.notte.cc"
