"""Tests for the `secret` proxy entry type."""

import json

import pytest
from notte_sdk import NotteClient
from notte_sdk.types import (
    ExternalProxy,
    NotteProxy,
    SecretProxy,
    SessionStartRequest,
    TailnetProxy,
)
from pydantic import ValidationError

from tests.sdk.test_generated_endpoints import fake
from tests.sdk.test_sessions_codegen import SESSION

PASSWORD = "proxy-password-value"  # pragma: allowlist secret
CA = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIU\n-----END CERTIFICATE-----\n"
KEY_LABEL = "PRIVATE KEY"
PRIVATE_KEY = f"-----BEGIN {KEY_LABEL}-----\n{'privatekeymaterial' * 20}\n-----END {KEY_LABEL}-----\n"


def secret_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "type": "secret",
        "server": "https://relay.example.com:443",
        "username": "proxy-user",
        "password": PASSWORD,
        "ca_certificate": CA,
        "hosts": ["api.stripe.com", "*.adyen.com"],
    }
    entry.update(overrides)
    return entry


def validation_error(proxies: list[dict[str, object]]) -> str:
    with pytest.raises(ValidationError) as error:
        SessionStartRequest.model_validate({"proxies": proxies})
    message = str(error.value)
    assert PASSWORD not in message
    assert "privatekeymaterial" not in message
    return message


class TestSecretProxyModel:
    def test_full_entry(self):
        proxy = SecretProxy.model_validate(secret_entry())
        assert proxy.type == "secret"
        assert proxy.server == "https://relay.example.com:443"
        assert proxy.username == "proxy-user"
        assert proxy.password == PASSWORD
        assert proxy.ca_certificate == CA
        assert proxy.hosts == ["api.stripe.com", "*.adyen.com"]

    def test_minimal_entry(self):
        proxy = SecretProxy(server="http://relay.example.com:8080", hosts=["checkout.example.com"])
        assert proxy.username is None
        assert proxy.password is None
        assert proxy.ca_certificate is None

    def test_password_is_not_in_repr(self):
        proxy = SecretProxy.model_validate(secret_entry())
        assert PASSWORD not in repr(proxy)
        assert PASSWORD not in str(proxy)
        request = SessionStartRequest(proxies=[NotteProxy(), proxy])
        assert PASSWORD not in repr(request)

    def test_password_is_sent(self):
        request = SessionStartRequest(proxies=[SecretProxy.model_validate(secret_entry())])
        assert request.model_dump(exclude_none=True)["proxies"] == [secret_entry()]

    @pytest.mark.parametrize("hosts", [["example.com"], ["*.example.com"], ["a.b.example.com", "*.c.example.com"]])
    def test_valid_hosts(self, hosts: list[str]):
        assert SecretProxy(server="https://relay.example.com:443", hosts=hosts).hosts == hosts

    def test_hosts_required_with_server(self):
        message = validation_error([{k: v for k, v in secret_entry().items() if k != "hosts"}])
        assert "hosts are required with server" in message

    def test_saved_configuration(self):
        # No server: the workspace's saved secret proxy fills in the entry.
        assert SecretProxy().server is None
        assert SecretProxy().hosts is None
        override = SecretProxy(hosts=["api.stripe.com"], password=PASSWORD)
        assert (override.server, override.hosts) == (None, ["api.stripe.com"])
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte"}, {"type": "secret"}]})
        assert isinstance(request.proxies, list)
        assert isinstance(request.proxies[1], SecretProxy)

    def test_hosts_are_checked_without_surrounding_whitespace(self):
        assert SecretProxy(server="https://relay.example.com:443", hosts=[" api.stripe.com "]).hosts == [
            " api.stripe.com "
        ]

    def test_hosts_not_empty(self):
        message = validation_error([secret_entry(hosts=[])])
        assert "hosts" in message

    @pytest.mark.parametrize(
        "host",
        [
            "*",
            "",
            "*.",
            "**.example.com",
            "api.*.example.com",
            "example.*",
            "example.com:443",
            "example.com/pay",
            "https://example.com",
            "exa mple.com",
            "example..com",
        ],
    )
    def test_invalid_hosts(self, host: str):
        message = validation_error([secret_entry(hosts=["api.stripe.com", host])])
        assert "must be an exact hostname or a leading '*.' wildcard" in message

    @pytest.mark.parametrize("server", ["relay.example.com:443", "socks5://relay.example.com:1080", "https://"])
    def test_invalid_server(self, server: str):
        message = validation_error([secret_entry(server=server)])
        assert "server must be http://host:port or https://host:port" in message

    def test_private_key_rejected(self):
        message = validation_error([secret_entry(ca_certificate=CA + PRIVATE_KEY)])
        assert "contains a private key" in message
        assert "rotate" in message

    @pytest.mark.parametrize("label", ["RSA PRIVATE KEY", "EC PRIVATE KEY", "ENCRYPTED PRIVATE KEY"])
    def test_typed_private_keys_rejected(self, label: str):
        key = f"-----BEGIN {label}-----\nprivatekeymaterial\n-----END {label}-----\n"
        message = validation_error([secret_entry(ca_certificate=key)])
        assert "contains a private key" in message

    def test_direct_construction_errors_hide_the_password(self):
        with pytest.raises(ValidationError) as error:
            SecretProxy(server="ftp://relay.example.com", password=PASSWORD, hosts=["*"])
        assert PASSWORD not in str(error.value)

    def test_unknown_field_rejected(self):
        validation_error([secret_entry(bypass="localhost")])


class TestSecretProxyCombinations:
    def test_with_notte_exit(self):
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte", "country": "gb"}, secret_entry()]})
        assert isinstance(request.proxies, list)
        assert isinstance(request.proxies[0], NotteProxy)
        assert isinstance(request.proxies[1], SecretProxy)

    def test_with_external_exit(self):
        request = SessionStartRequest(
            proxies=[ExternalProxy(server="http://exit.example.com:8080"), SecretProxy.model_validate(secret_entry())]
        )
        assert isinstance(request.proxies, list)
        assert [proxy.type for proxy in request.proxies] == ["external", "secret"]

    def test_alone(self):
        request = SessionStartRequest.model_validate({"proxies": [secret_entry()]})
        assert isinstance(request.proxies, list)
        assert isinstance(request.proxies[0], SecretProxy)

    def test_at_most_one(self):
        message = validation_error([secret_entry(), secret_entry(hosts=["example.com"])])
        assert "At most one `secret` proxy" in message

    def test_not_with_tailnet(self):
        message = validation_error([{"type": "tailnet"}, secret_entry()])
        assert "cannot be combined with a `tailnet` proxy" in message

    def test_not_with_tailnet_models(self):
        with pytest.raises(ValidationError, match="tailnet"):
            SessionStartRequest(proxies=[TailnetProxy(), SecretProxy.model_validate(secret_entry())])

    def test_local_sessions_reject_it(self):
        request = SessionStartRequest.model_validate({"proxies": [secret_entry()]})
        with pytest.raises(NotImplementedError, match="Secret proxy only supported in cloud"):
            _ = request.playwright_proxy


class TestSecretProxyWire:
    def test_dict_entry_is_sent_unchanged(self, monkeypatch: pytest.MonkeyPatch):
        proxies = [{"type": "notte", "country": "gb"}, secret_entry()]
        api = fake(monkeypatch, SESSION)
        NotteClient(api_key="test").sessions.start(proxies=proxies)  # pragma: allowlist secret
        assert json.loads(api.calls[0].data)["proxies"] == proxies

    def test_model_entry_is_sent(self, monkeypatch: pytest.MonkeyPatch):
        api = fake(monkeypatch, SESSION)
        NotteClient(api_key="test").sessions.start(  # pragma: allowlist secret
            proxies=[NotteProxy(), SecretProxy(server="https://relay.example.com:443", hosts=["api.stripe.com"])]
        )
        sent = json.loads(api.calls[0].data)["proxies"]
        assert [proxy["type"] for proxy in sent] == ["notte", "secret"]
        assert {key: value for key, value in sent[1].items() if value is not None} == {
            "type": "secret",
            "server": "https://relay.example.com:443",
            "hosts": ["api.stripe.com"],
        }

    def test_dict_entry_becomes_a_secret_proxy(self):
        request = SessionStartRequest.from_data({"proxies": [secret_entry()]})
        assert isinstance(request.proxies, list)
        proxy = request.proxies[0]
        assert isinstance(proxy, SecretProxy)
        assert PASSWORD not in repr(proxy)

    def test_request_schema_is_concrete(self):
        # Request models are inputs only: the API publishes their validation schema.
        schema = SecretProxy.model_json_schema(mode="validation")
        assert schema["type"] == "object"
        assert {"type", "server", "username", "password", "ca_certificate", "hosts"} <= set(schema["properties"])
        assert "required" not in schema
        session_schema = SessionStartRequest.model_json_schema(mode="validation")
        assert "SecretProxy" in session_schema["$defs"]
        proxies = json.dumps(session_schema["properties"]["proxies"])
        assert '"secret": "#/$defs/SecretProxy"' in proxies
