"""Comprehensive tests for the simplified proxy API."""

import pytest
from notte_sdk.types import (
    ExternalProxy,
    NotteProxy,
    ProxyGeolocationCountry,
    SessionStartRequest,
)
from pydantic import ValidationError


class TestDirectProxyValidation:
    """Test ProxySettings.model_validate() with various dictionary inputs."""

    def test_notte_proxy_with_country_string(self):
        """Test NotteProxy with country as string."""
        proxy = NotteProxy.model_validate({"type": "notte", "country": "us"})
        assert proxy.type == "notte"
        assert proxy.country == ProxyGeolocationCountry.UNITED_STATES
        assert proxy.id is None

    def test_notte_proxy_with_country_enum(self):
        """Test NotteProxy with country as enum."""
        proxy = NotteProxy.model_validate({"type": "notte", "country": ProxyGeolocationCountry.UNITED_KINGDOM})
        assert proxy.type == "notte"
        assert proxy.country == ProxyGeolocationCountry.UNITED_KINGDOM

    def test_notte_proxy_without_country(self):
        """Test NotteProxy without country (None)."""
        proxy = NotteProxy.model_validate({"type": "notte"})
        assert proxy.type == "notte"
        assert proxy.country is None
        assert proxy.id is None

    def test_notte_proxy_with_id(self):
        """Test NotteProxy with id."""
        proxy = NotteProxy.model_validate({"type": "notte", "id": "my-proxy-id", "country": "ca"})
        assert proxy.type == "notte"
        assert proxy.id == "my-proxy-id"
        assert proxy.country == ProxyGeolocationCountry.CANADA

    def test_external_proxy_minimal(self):
        """Test ExternalProxy with minimal fields (server only)."""
        proxy = ExternalProxy.model_validate({"type": "external", "server": "http://proxy.example.com:8080"})
        assert proxy.type == "external"
        assert proxy.server == "http://proxy.example.com:8080"
        assert proxy.username is None
        assert proxy.password is None
        assert proxy.bypass is None

    def test_external_proxy_with_all_fields(self):
        """Test ExternalProxy with all fields."""
        proxy = ExternalProxy.model_validate(
            {
                "type": "external",
                "server": "http://proxy.example.com:8080",
                "username": "testuser",
                "password": "testpass",  # pragma: allowlist secret
                "bypass": "localhost,127.0.0.1",
            }
        )
        assert proxy.type == "external"
        assert proxy.server == "http://proxy.example.com:8080"
        assert proxy.username == "testuser"
        assert proxy.password == "testpass"  # pragma: allowlist secret
        assert proxy.bypass == "localhost,127.0.0.1"

    def test_invalid_proxy_type(self):
        """Test that invalid proxy type fails validation."""
        with pytest.raises(ValidationError, match="type"):
            NotteProxy.model_validate({"type": "invalid"})


class TestSessionStartRequestWithStringCountryCodes:
    """Test SessionStartRequest with string country code shortcuts."""

    def test_string_country_us(self):
        """Test proxies='us' string shorthand."""
        request = SessionStartRequest.model_validate({"proxies": "us"})
        assert isinstance(request.proxies, list)
        assert len(request.proxies) == 1
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country == ProxyGeolocationCountry.UNITED_STATES

    def test_string_country_gb(self):
        """Test proxies='gb' string shorthand."""
        request = SessionStartRequest.model_validate({"proxies": "gb"})
        assert isinstance(request.proxies, list)
        assert len(request.proxies) == 1
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country == ProxyGeolocationCountry.UNITED_KINGDOM

    def test_string_country_fr(self):
        """Test proxies='fr' string shorthand."""
        request = SessionStartRequest.model_validate({"proxies": "fr"})
        assert isinstance(request.proxies, list)
        assert len(request.proxies) == 1
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country == ProxyGeolocationCountry.FRANCE

    def test_invalid_country_code(self):
        """Test that invalid country code fails validation."""
        with pytest.raises(ValidationError):
            SessionStartRequest.model_validate({"proxies": "invalid"})


class TestSessionStartRequestWithDictConfigs:
    """Test SessionStartRequest with dictionary proxy configurations."""

    def test_notte_proxy_dict_with_country(self):
        """Test NotteProxy dict: {"type": "notte", "country": "us"}."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte", "country": "us"}]})
        assert isinstance(request.proxies, list)
        assert len(request.proxies) == 1
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country == ProxyGeolocationCountry.UNITED_STATES

    def test_notte_proxy_dict_with_typo_in_country(self):
        """Test NotteProxy dict with typo in 'country' field should fail validation."""
        # The typo "coutnry" is rejected because pydantic has extra="forbid"
        with pytest.raises(ValidationError, match="coutnry"):
            SessionStartRequest.model_validate({"proxies": [{"type": "notte", "coutnry": "us"}]})

    def test_notte_proxy_dict_minimal(self):
        """Test NotteProxy dict minimal: {"type": "notte"}."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte"}]})
        assert isinstance(request.proxies, list)
        assert len(request.proxies) == 1
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country is None

    def test_notte_proxy_dict_with_id(self):
        """Test NotteProxy dict with id: {"type": "notte", "id": "my-proxy", "country": "ca"}."""
        request = SessionStartRequest.model_validate(
            {"proxies": [{"type": "notte", "id": "my-proxy", "country": "ca"}]}
        )
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].id == "my-proxy"
        assert request.proxies[0].country == ProxyGeolocationCountry.CANADA

    def test_external_proxy_dict(self):
        """Test ExternalProxy dict."""
        request = SessionStartRequest.model_validate(
            {"proxies": [{"type": "external", "server": "http://proxy.example.com:8080"}]}
        )
        assert request.proxies[0].type == "external"
        assert request.proxies[0].server == "http://proxy.example.com:8080"

    def test_external_proxy_dict_with_auth(self):
        """Test ExternalProxy dict with authentication."""
        request = SessionStartRequest.model_validate(
            {
                "proxies": [
                    {
                        "type": "external",
                        "server": "http://proxy.example.com:8080",
                        "username": "user",
                        "password": "pass",  # pragma: allowlist secret
                    }
                ]
            }
        )
        assert request.proxies[0].type == "external"
        assert request.proxies[0].server == "http://proxy.example.com:8080"
        assert request.proxies[0].username == "user"
        assert request.proxies[0].password == "pass"  # pragma: allowlist secret


class TestSessionStartRequestWithBooleanValues:
    """Test SessionStartRequest with boolean proxy values."""

    def test_proxies_true(self):
        """Test proxies=True (default Notte proxy)."""
        request = SessionStartRequest.model_validate({"proxies": True})
        assert request.proxies is True

    def test_proxies_false(self):
        """Test proxies=False (no proxy)."""
        request = SessionStartRequest.model_validate({"proxies": False})
        assert request.proxies is False


class TestSessionStartRequestWithListConfigs:
    """Test SessionStartRequest with list of proxy configs."""

    def test_list_with_notte_proxy(self):
        """Test proxies=[{"type": "notte"}]."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte"}]})
        assert isinstance(request.proxies, list)
        assert len(request.proxies) == 1
        assert request.proxies[0].type == "notte"

    def test_list_with_notte_proxy_and_country(self):
        """Test proxies=[{"type": "notte", "country": "de"}]."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte", "country": "de"}]})
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country == ProxyGeolocationCountry.GERMANY

    def test_list_with_external_proxy(self):
        """Test proxies=[{"type": "external", "server": "http://localhost:8080"}]."""
        request = SessionStartRequest.model_validate(
            {"proxies": [{"type": "external", "server": "http://localhost:8080"}]}
        )
        assert request.proxies[0].type == "external"
        assert request.proxies[0].server == "http://localhost:8080"


class TestBackwardCompatibility:
    """Test backward compatibility with old geolocation syntax."""

    def test_notte_proxy_with_geolocation_dict(self):
        """Test NotteProxy.model_validate with old geolocation syntax."""
        proxy = NotteProxy.model_validate({"type": "notte", "geolocation": {"country": "us"}})
        assert proxy.type == "notte"
        assert proxy.country == ProxyGeolocationCountry.UNITED_STATES
        # geolocation should not exist as a field
        assert not hasattr(proxy, "geolocation")

    def test_session_start_request_with_geolocation_list(self):
        """Test SessionStartRequest with old geolocation syntax in list."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte", "geolocation": {"country": "gb"}}]})
        assert request.proxies[0].type == "notte"
        assert request.proxies[0].country == ProxyGeolocationCountry.UNITED_KINGDOM

    def test_geolocation_with_country_already_set(self):
        """Test that country field takes precedence if both are provided."""
        proxy = NotteProxy.model_validate({"type": "notte", "country": "us", "geolocation": {"country": "gb"}})
        # country should take precedence over geolocation
        assert proxy.country == ProxyGeolocationCountry.UNITED_STATES

    def test_geolocation_with_id(self):
        """Test old geolocation syntax with id field."""
        proxy = NotteProxy.model_validate({"type": "notte", "id": "test-proxy", "geolocation": {"country": "ca"}})
        assert proxy.id == "test-proxy"
        assert proxy.country == ProxyGeolocationCountry.CANADA


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    def test_empty_string_country_code(self):
        """Test empty string country code fails validation."""
        with pytest.raises(ValidationError):
            SessionStartRequest.model_validate({"proxies": ""})

    def test_invalid_country_code_format(self):
        """Test invalid country code format fails validation."""
        with pytest.raises(ValidationError):
            SessionStartRequest.model_validate({"proxies": "invalid_code"})

    def test_external_proxy_missing_server(self):
        """Test ExternalProxy missing required server field."""
        with pytest.raises(ValidationError, match="server"):
            SessionStartRequest.model_validate({"proxies": [{"type": "external"}]})

    def test_multiple_proxies_should_raise_error(self):
        """Test that multiple proxies in list raises error when accessing playwright_proxy."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte"}, {"type": "notte"}]})
        with pytest.raises(ValueError, match="Multiple proxies are not supported"):
            _ = request.playwright_proxy

    def test_dict_without_type_field(self):
        """Test dictionary without 'type' field fails validation."""
        with pytest.raises(ValidationError, match="type"):
            SessionStartRequest.model_validate({"proxies": [{"country": "us"}]})

    def test_empty_list_proxies(self):
        """Test empty list should disable proxies."""
        request = SessionStartRequest.model_validate({"proxies": []})
        assert request.proxies == []
        assert request.playwright_proxy is None

    def test_notte_proxy_playwright_proxy_raises_error(self):
        """Test that Notte proxy raises NotImplementedError for local sessions."""
        request = SessionStartRequest.model_validate({"proxies": [{"type": "notte", "country": "us"}]})
        with pytest.raises(NotImplementedError, match="Notte proxy only supported in cloud"):
            _ = request.playwright_proxy

    def test_external_proxy_playwright_proxy_works(self):
        """Test that external proxy works with playwright_proxy."""
        request = SessionStartRequest.model_validate(
            {"proxies": [{"type": "external", "server": "http://localhost:8080"}]}
        )
        playwright_proxy = request.playwright_proxy
        assert playwright_proxy is not None
        assert playwright_proxy["server"] == "http://localhost:8080"
