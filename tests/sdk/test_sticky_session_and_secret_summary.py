"""Tests for `NotteProxy.sticky_session` and the session response's `secret_proxy` summary."""

import json
from typing import Literal

import pytest
from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, SecretProxySummary, SessionResponse, SessionStartRequest
from pydantic import ValidationError

from tests.sdk.test_generated_endpoints import fake
from tests.sdk.test_sessions_codegen import SESSION


def sent_proxies(monkeypatch: pytest.MonkeyPatch, proxies: object) -> list[dict[str, object]]:
    api = fake(monkeypatch, SESSION)
    client = NotteClient(api_key="test")  # pragma: allowlist secret
    client.sessions.start(proxies=proxies)  # pyright: ignore[reportArgumentType]
    return json.loads(api.calls[0].data)["proxies"]


class TestStickySession:
    @pytest.mark.parametrize("value", ["a", "checkout-42", "A1-b2-C3", "x" * 64])
    def test_valid(self, value: str):
        assert NotteProxy(sticky_session=value).sticky_session == value

    @pytest.mark.parametrize("value", ["", "x" * 65, "has space", "under_score", "dot.ted", "slash/"])
    def test_invalid(self, value: str):
        with pytest.raises(ValidationError, match="sticky_session"):
            NotteProxy(sticky_session=value)

    def test_invalid_in_session_request(self):
        with pytest.raises(ValidationError, match="sticky_session"):
            SessionStartRequest.model_validate({"proxies": [{"type": "notte", "sticky_session": "no spaces"}]})

    def test_defaults_to_none(self):
        assert NotteProxy().sticky_session is None
        assert NotteProxy.from_country("us").sticky_session is None
        assert NotteProxy.from_city("Paris").sticky_session is None

    def test_helpers(self):
        by_country = NotteProxy.from_country("gb", sticky_session="checkout-1")
        assert (by_country.country, by_country.sticky_session) == ("gb", "checkout-1")
        by_city = NotteProxy.from_city("Paris", proxy_id="p", sticky_session="checkout-2")
        assert (by_city.id, by_city.city, by_city.sticky_session) == ("p", "Paris", "checkout-2")

    def test_unset_is_not_sent(self, monkeypatch: pytest.MonkeyPatch):
        # APIs that predate the field reject it, even as null.
        sent = sent_proxies(monkeypatch, [NotteProxy(), NotteProxy.from_country("us"), NotteProxy.from_city("Paris")])
        assert all("sticky_session" not in proxy for proxy in sent)
        assert sent[0] == {"type": "notte", "id": None, "country": None, "city": None}

    def test_model_is_sent(self, monkeypatch: pytest.MonkeyPatch):
        sent = sent_proxies(monkeypatch, [NotteProxy(country="gb", sticky_session="checkout-1")])
        assert sent[0]["sticky_session"] == "checkout-1"
        assert sent[0]["country"] == "gb"

    def test_helpers_are_sent(self, monkeypatch: pytest.MonkeyPatch):
        sent = sent_proxies(
            monkeypatch,
            [NotteProxy.from_country("gb", sticky_session="s1"), NotteProxy.from_city("Paris", sticky_session="s2")],
        )
        assert [proxy["sticky_session"] for proxy in sent] == ["s1", "s2"]

    def test_dict_is_sent_unchanged(self, monkeypatch: pytest.MonkeyPatch):
        proxies = [{"type": "notte", "country": "gb", "sticky_session": "checkout-1"}]
        assert sent_proxies(monkeypatch, proxies) == proxies

    def test_validation_schema(self):
        prop = NotteProxy.model_json_schema(mode="validation")["properties"]["sticky_session"]
        assert {"pattern": "^[A-Za-z0-9-]{1,64}$", "type": "string"} in prop["anyOf"]
        assert "sticky_session" not in NotteProxy.model_json_schema(mode="validation").get("required", [])


SUMMARY = {
    "server": "https://relay.example.com:443",
    "hosts": ["api.stripe.com", "*.adyen.com"],
    "ca_sha256": ["ab" * 32],
}


class TestSecretProxySummary:
    def test_absent_by_default(self):
        response = SessionResponse.model_validate(SESSION)
        assert response.secret_proxy is None
        assert "secret_proxy" not in json.loads(response.model_dump_json(exclude_none=True))

    def test_parsed(self):
        response = SessionResponse.model_validate({**SESSION, "secret_proxy": SUMMARY})
        assert isinstance(response.secret_proxy, SecretProxySummary)
        assert response.secret_proxy.server == SUMMARY["server"]
        assert response.secret_proxy.hosts == SUMMARY["hosts"]
        assert response.secret_proxy.ca_sha256 == SUMMARY["ca_sha256"]
        assert json.loads(response.model_dump_json(exclude_none=True))["secret_proxy"] == SUMMARY

    def test_returned_by_start(self, monkeypatch: pytest.MonkeyPatch):
        _ = fake(monkeypatch, {**SESSION, "secret_proxy": SUMMARY})
        response = NotteClient(api_key="test").sessions.start()  # pragma: allowlist secret
        assert response.secret_proxy == SecretProxySummary.model_validate(SUMMARY)

    @pytest.mark.parametrize("mode", ["validation", "serialization"])
    def test_schemas_are_concrete(self, mode: Literal["validation", "serialization"]):
        summary = SecretProxySummary.model_json_schema(mode=mode)
        assert summary["type"] == "object"
        assert set(summary["required"]) == {"server", "hosts", "ca_sha256"}
        session = SessionResponse.model_json_schema(mode=mode)
        assert session["type"] == "object"
        assert "secret_proxy" not in session["required"]
        assert {"$ref": "#/$defs/SecretProxySummary"} in session["properties"]["secret_proxy"]["anyOf"]
