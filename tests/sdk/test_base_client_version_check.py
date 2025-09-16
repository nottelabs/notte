from unittest.mock import MagicMock, patch

import pytest
import requests
from notte_sdk.endpoints.base import BaseClient, _cached_pypi_version, _version_check_performed
from pydantic import ValidationError


class MockNotteClient:
    """Mock NotteClient for testing BaseClient."""

    pass


@pytest.fixture
def api_key() -> str:
    return "test-api-key"


@pytest.fixture
def reset_global_state():
    """Reset global version check state before each test."""
    global _cached_pypi_version, _version_check_performed
    # Store original values
    original_cached = _cached_pypi_version
    original_performed = _version_check_performed

    # Reset to initial state
    import notte_sdk.endpoints.base as base_module

    base_module._cached_pypi_version = None
    base_module._version_check_performed = False

    yield

    # Restore original values after test
    base_module._cached_pypi_version = original_cached
    base_module._version_check_performed = original_performed


@pytest.fixture
def mock_pypi_response():
    """Mock successful PyPI API response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"info": {"version": "1.7.2"}}
    mock_response.raise_for_status.return_value = None
    return mock_response


class TestBaseClientVersionCheck:
    """Test suite for BaseClient version checking functionality."""

    def test_version_check_skipped_for_dev_version(self, api_key: str, reset_global_state):
        """Test that version check is skipped for development versions containing '.dev'."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.4.4.dev0"):
            with patch("requests.get") as mock_get:
                # Create BaseClient - should skip version check for .dev version
                _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                # Verify no PyPI request was made
                mock_get.assert_not_called()

                # Verify global state
                import notte_sdk.endpoints.base as base_module

                assert base_module._version_check_performed is True  # Flag should be set
                assert base_module._cached_pypi_version is None  # But no version cached

    def test_version_check_performed_for_production_version(self, api_key: str, reset_global_state, mock_pypi_response):
        """Test that version check is performed for production versions."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get", return_value=mock_pypi_response) as mock_get:
                # Create BaseClient - should perform version check for production version
                _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                # Verify PyPI request was made
                mock_get.assert_called_once()

                # Check the request details
                call_args = mock_get.call_args
                assert "https://pypi.org/pypi/notte-sdk/json" in call_args[0][0]
                assert call_args[1]["headers"]["User-Agent"].startswith("notte-sdk/")

                # Verify global state
                import notte_sdk.endpoints.base as base_module

                assert base_module._version_check_performed is True
                assert base_module._cached_pypi_version == "1.7.2"

    def test_version_mismatch_warning_logged(self, api_key: str, reset_global_state, mock_pypi_response):
        """Test that a warning is logged when there's a version mismatch."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get", return_value=mock_pypi_response):
                with patch("notte_sdk.endpoints.base.logger.warning") as mock_logger:
                    # Create BaseClient - should warn about version mismatch
                    _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                    # Check that warning was logged
                    mock_logger.assert_called_once()
                    warning_message = mock_logger.call_args[0][0]
                    assert "⚠️ You are using notte-sdk version 1.5.0" in warning_message
                    assert "but version 1.7.2 is available on PyPI" in warning_message
                    assert "pip install notte-sdk==1.7.2" in warning_message

    def test_no_warning_when_versions_match(self, api_key: str, reset_global_state):
        """Test that no warning is logged when versions match."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "1.5.0"}}
        mock_response.raise_for_status.return_value = None

        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get", return_value=mock_response):
                with patch("notte_sdk.endpoints.base.logger.warning") as mock_logger:
                    # Create BaseClient - versions match, no warning expected
                    _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                    # Check that no warning was logged
                    mock_logger.assert_not_called()

    def test_version_check_only_performed_once(self, api_key: str, reset_global_state, mock_pypi_response):
        """Test that version check is only performed once per process."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get", return_value=mock_pypi_response) as mock_get:
                # Create first BaseClient
                _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                # Create second BaseClient
                _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                # Verify PyPI request was made only once
                assert mock_get.call_count == 1

                # Verify global state
                import notte_sdk.endpoints.base as base_module

                assert base_module._version_check_performed is True
                assert base_module._cached_pypi_version == "1.7.2"

    def test_version_check_silent_failure_on_network_error(self, api_key: str, reset_global_state):
        """Test that version check fails silently on network errors."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get", side_effect=requests.RequestException("Network error")):
                with patch("notte_sdk.endpoints.base.logger.warning") as mock_logger:
                    # Create BaseClient - should handle network error silently
                    _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                    # Check that no warning was logged
                    mock_logger.assert_not_called()

                    # Verify global state
                    import notte_sdk.endpoints.base as base_module

                    assert base_module._version_check_performed is True
                    assert base_module._cached_pypi_version is None

    def test_version_check_silent_failure_on_json_error(self, api_key: str, reset_global_state):
        """Test that version check fails silently on JSON parsing errors."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}  # Missing 'info' key
        mock_response.raise_for_status.return_value = None

        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get", return_value=mock_response):
                with patch("notte_sdk.endpoints.base.logger.warning") as mock_logger:
                    # Create BaseClient - should handle JSON error silently
                    _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                    # Check that no warning was logged
                    mock_logger.assert_not_called()

                    # Verify global state
                    import notte_sdk.endpoints.base as base_module

                    assert base_module._version_check_performed is True
                    assert base_module._cached_pypi_version is None

    def test_private_get_latest_pypi_version_method(self, api_key: str, mock_pypi_response):
        """Test the private _get_latest_pypi_version method directly."""
        with patch("requests.get", return_value=mock_pypi_response) as mock_get:
            client = BaseClient(MockNotteClient(), None, api_key=api_key)

            # Test the private method directly
            version = client._get_latest_pypi_version("test-package")

            assert version == "1.7.2"

            # Verify request details
            call_args = mock_get.call_args
            assert "https://pypi.org/pypi/test-package/json" in call_args[0][0]
            assert "User-Agent" in call_args[1]["headers"]

    def test_private_method_raises_on_http_error(self, api_key: str):
        """Test that _get_latest_pypi_version raises on HTTP errors."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        with patch("requests.get", return_value=mock_response):
            client = BaseClient(MockNotteClient(), None, api_key=api_key)

            with pytest.raises(requests.HTTPError):
                _ = client._get_latest_pypi_version("nonexistent-package")

    def test_private_method_raises_on_key_error(self, api_key: str):
        """Test that _get_latest_pypi_version raises on missing keys."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}
        mock_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=mock_response):
            client = BaseClient(MockNotteClient(), None, api_key=api_key)

            with pytest.raises(KeyError):
                _ = client._get_latest_pypi_version("test-package")

    def test_user_agent_header_format(self, api_key: str, reset_global_state):
        """Test that the User-Agent header is properly formatted."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"info": {"version": "1.7.2"}}
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                # Check User-Agent header format
                call_args = mock_get.call_args
                user_agent = call_args[1]["headers"]["User-Agent"]
                assert user_agent.startswith("notte-sdk/")
                assert "(https://github.com/NotteAI/notte)" in user_agent

    def test_timeout_configuration(self, api_key: str, reset_global_state):
        """Test that the request uses the correct timeout."""
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.5.0"):
            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"info": {"version": "1.7.2"}}
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                _ = BaseClient(MockNotteClient(), None, api_key=api_key)

                # Check timeout parameter
                call_args = mock_get.call_args
                assert call_args[1]["timeout"] == BaseClient.DEFAULT_REQUEST_TIMEOUT_SECONDS

    def test_version_comparison_logic(self, api_key: str, reset_global_state):
        """Test the version comparison logic in _should_suggest_upgrade method."""
        client = BaseClient(MockNotteClient(), None, api_key=api_key)

        # Test with no cached version
        import notte_sdk.endpoints.base as base_module

        base_module._cached_pypi_version = None
        should_upgrade, cached_version = client._should_suggest_upgrade()
        assert should_upgrade is False
        assert cached_version is None

        # Test with newer cached version
        base_module._cached_pypi_version = "1.8.0"
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.7.0"):
            should_upgrade, cached_version = client._should_suggest_upgrade()
            assert should_upgrade is True
            assert cached_version == "1.8.0"

        # Test with same versions
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.8.0"):
            should_upgrade, cached_version = client._should_suggest_upgrade()
            assert should_upgrade is False
            assert cached_version == "1.8.0"

        # Test with older cached version
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.9.0"):
            should_upgrade, cached_version = client._should_suggest_upgrade()
            assert should_upgrade is False
            assert cached_version == "1.8.0"

        # Test with development version (should not suggest upgrade)
        with patch("notte_sdk.endpoints.base.notte_core_version", "1.7.0.dev0"):
            should_upgrade, cached_version = client._should_suggest_upgrade()
            assert should_upgrade is False
            assert cached_version == "1.8.0"

    def test_pydantic_validation_error_with_upgrade_suggestion(self, api_key: str, reset_global_state):
        """Test that ValidationError is enhanced with upgrade message when version is outdated."""
        from notte_sdk.endpoints.base import NotteEndpoint
        from pydantic import BaseModel

        class MockResponse(BaseModel):
            field: str

        # Create a mock endpoint
        mock_endpoint = NotteEndpoint(path="/test", response=MockResponse, method="GET")

        # Set up version state to suggest upgrade
        import notte_sdk.endpoints.base as base_module

        base_module._cached_pypi_version = "1.8.0"

        with patch("notte_sdk.endpoints.base.notte_core_version", "1.7.0"):
            # Mock PyPI response to return our test version
            mock_pypi_response = MagicMock()
            mock_pypi_response.status_code = 200
            mock_pypi_response.json.return_value = {"info": {"version": "1.8.0"}}
            mock_pypi_response.raise_for_status.return_value = None

            with patch("requests.get", return_value=mock_pypi_response):
                with patch.object(BaseClient, "_request") as mock_request:
                    # Mock a response that will cause validation error
                    mock_request.return_value = {"unexpected_field": "value"}

                    client = BaseClient(MockNotteClient(), None, api_key=api_key)

                with pytest.raises(RuntimeError) as exc_info:
                    client.request(mock_endpoint)

                # Check that the error message contains upgrade suggestion
                error_message = str(exc_info.value)
                assert "Pydantic validation failed" in error_message
                assert "API schema changes" in error_message
                assert "Current SDK version: 1.7.0" in error_message
                assert "Latest available: 1.8.0" in error_message
                assert "pip install notte-sdk==1.8.0" in error_message

    def test_pydantic_validation_error_without_upgrade_suggestion(self, api_key: str, reset_global_state):
        """Test that ValidationError is not enhanced when no upgrade needed."""
        from notte_sdk.endpoints.base import NotteEndpoint
        from pydantic import BaseModel

        class MockResponse(BaseModel):
            field: str

        # Create a mock endpoint
        mock_endpoint = NotteEndpoint(path="/test", response=MockResponse, method="GET")

        # Set up version state where upgrade is not needed
        import notte_sdk.endpoints.base as base_module

        base_module._cached_pypi_version = "1.7.0"

        with patch("notte_sdk.endpoints.base.notte_core_version", "1.8.0"):  # Current version is newer
            with patch.object(BaseClient, "_request") as mock_request:
                # Mock a response that will cause validation error
                mock_request.return_value = {"unexpected_field": "value"}

                client = BaseClient(MockNotteClient(), None, api_key=api_key)

                with pytest.raises(ValidationError) as exc_info:
                    client.request(mock_endpoint)

                # Check that the error message is the original Pydantic error
                error_message = str(exc_info.value)
                assert "Pydantic validation failed" not in error_message  # Should not have our custom message
                assert "API schema changes" not in error_message

    def test_pydantic_validation_error_with_no_cached_version(self, api_key: str, reset_global_state):
        """Test that ValidationError is not enhanced when no cached version available."""
        from notte_sdk.endpoints.base import NotteEndpoint
        from pydantic import BaseModel

        class MockResponse(BaseModel):
            field: str

        # Create a mock endpoint
        mock_endpoint = NotteEndpoint(path="/test", response=MockResponse, method="GET")

        # Set up version state with no cached version
        import notte_sdk.endpoints.base as base_module

        base_module._cached_pypi_version = None

        with patch("notte_sdk.endpoints.base.notte_core_version", "1.7.0"):
            # Mock PyPI to fail so no cached version is set
            with patch("requests.get", side_effect=requests.RequestException("Network error")):
                with patch.object(BaseClient, "_request") as mock_request:
                    # Mock a response that will cause validation error
                    mock_request.return_value = {"unexpected_field": "value"}

                    client = BaseClient(MockNotteClient(), None, api_key=api_key)

                    with pytest.raises(ValidationError) as exc_info:
                        client.request(mock_endpoint)

                    # Check that the error message is the original Pydantic error
                    error_message = str(exc_info.value)
                    assert "Pydantic validation failed" not in error_message  # Should not have our custom message

    def test_pydantic_validation_error_in_request_list_with_upgrade(self, api_key: str, reset_global_state):
        """Test that ValidationError in request_list is enhanced with upgrade message when appropriate."""
        from notte_sdk.endpoints.base import NotteEndpoint
        from pydantic import BaseModel

        class MockResponse(BaseModel):
            field: str

        # Create a mock endpoint
        mock_endpoint = NotteEndpoint(path="/test", response=MockResponse, method="GET")

        # Set up version state to suggest upgrade
        import notte_sdk.endpoints.base as base_module

        base_module._cached_pypi_version = "1.8.0"

        with patch("notte_sdk.endpoints.base.notte_core_version", "1.7.0"):
            # Mock PyPI response to return our test version
            mock_pypi_response = MagicMock()
            mock_pypi_response.status_code = 200
            mock_pypi_response.json.return_value = {"info": {"version": "1.8.0"}}
            mock_pypi_response.raise_for_status.return_value = None

            with patch("requests.get", return_value=mock_pypi_response):
                with patch.object(BaseClient, "_request") as mock_request:
                    # Mock a list response that will cause validation error
                    mock_request.return_value = [{"unexpected_field": "value"}]

                    client = BaseClient(MockNotteClient(), None, api_key=api_key)

                    with pytest.raises(RuntimeError) as exc_info:
                        client.request_list(mock_endpoint)

                    # Check that the error message contains upgrade suggestion for list response
                    error_message = str(exc_info.value)
                    assert "Pydantic validation failed for list response" in error_message
                    assert "API schema changes" in error_message
                    assert "Current SDK version: 1.7.0" in error_message
                    assert "Latest available: 1.8.0" in error_message
                    assert "pip install notte-sdk==1.8.0" in error_message

    def test_create_upgrade_error_message_method(self, api_key: str):
        """Test the _create_upgrade_error_message method directly."""
        client = BaseClient(MockNotteClient(), None, api_key=api_key)

        # Test with original error
        message = client._create_upgrade_error_message("Test validation failed", "1.8.0", "Original error message")

        assert "Test validation failed" in message
        assert "API schema changes" in message
        assert "Latest available: 1.8.0" in message
        assert "pip install notte-sdk==1.8.0" in message
        assert "Original error: Original error message" in message

        # Test without original error
        message2 = client._create_upgrade_error_message("Another test error", "1.8.0")

        assert "Another test error" in message2
        assert "API schema changes" in message2
        assert "Latest available: 1.8.0" in message2
        assert "pip install notte-sdk==1.8.0" in message2
        assert "Original error:" not in message2
