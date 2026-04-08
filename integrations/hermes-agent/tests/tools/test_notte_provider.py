"""Tests for the Notte cloud browser provider."""

from unittest.mock import Mock, patch

import pytest


class TestNotteProviderName:
    def test_returns_notte(self):
        from tools.browser_providers.notte import NotteProvider

        assert NotteProvider().provider_name() == "Notte"


class TestNotteIsConfigured:
    def test_configured_when_api_key_set(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test-key-123")
        from tools.browser_providers.notte import NotteProvider

        assert NotteProvider().is_configured() is True

    def test_not_configured_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("NOTTE_API_KEY", raising=False)
        from tools.browser_providers.notte import NotteProvider

        assert NotteProvider().is_configured() is False

    def test_not_configured_when_api_key_empty(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "")
        from tools.browser_providers.notte import NotteProvider

        assert NotteProvider().is_configured() is False


class TestNotteCreateSession:
    def test_create_session_returns_expected_dict(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test-key-123")
        from tools.browser_providers.notte import NotteProvider

        start_response = Mock()
        start_response.ok = True
        start_response.json.return_value = {"session_id": "sess_abc123"}

        debug_response = Mock()
        debug_response.ok = True
        debug_response.json.return_value = {
            "debug_url": "https://debug.notte.cc/sess_abc123",
            "ws": {
                "cdp": "wss://cdp.notte.cc/sess_abc123",
                "recording": "wss://rec.notte.cc/sess_abc123",
                "logs": "wss://logs.notte.cc/sess_abc123",
            },
            "tabs": [],
        }

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.post.return_value = start_response
            mock_requests.get.return_value = debug_response

            result = NotteProvider().create_session("task_42")

        assert result["bb_session_id"] == "sess_abc123"
        assert result["cdp_url"] == "wss://cdp.notte.cc/sess_abc123"
        assert result["session_name"].startswith("hermes_task_42_")
        assert result["features"]["proxies"] is True
        assert result["features"]["stealth"] is True

        # Verify correct API calls
        mock_requests.post.assert_called_once()
        call_args = mock_requests.post.call_args
        assert "/sessions/start" in call_args[0][0]
        assert call_args[1]["json"]["headless"] is True
        assert call_args[1]["json"]["proxies"] is True

        mock_requests.get.assert_called_once()
        get_args = mock_requests.get.call_args
        assert "/sessions/sess_abc123/debug" in get_args[0][0]

    def test_create_session_sends_auth_header(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-my-secret-key")
        from tools.browser_providers.notte import NotteProvider

        start_response = Mock()
        start_response.ok = True
        start_response.json.return_value = {"session_id": "sess_xyz"}

        debug_response = Mock()
        debug_response.ok = True
        debug_response.json.return_value = {
            "ws": {"cdp": "wss://cdp.notte.cc/sess_xyz", "recording": "", "logs": ""},
            "debug_url": "",
            "tabs": [],
        }

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.post.return_value = start_response
            mock_requests.get.return_value = debug_response

            NotteProvider().create_session("task_auth")

        headers = mock_requests.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer nk-my-secret-key"
        assert headers["x-notte-request-origin"] == "hermes-agent"

    def test_create_session_uses_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        monkeypatch.setenv("NOTTE_API_URL", "https://custom.notte.example")
        from tools.browser_providers.notte import NotteProvider

        start_response = Mock()
        start_response.ok = True
        start_response.json.return_value = {"session_id": "sess_custom"}

        debug_response = Mock()
        debug_response.ok = True
        debug_response.json.return_value = {
            "ws": {"cdp": "wss://cdp.custom/sess_custom", "recording": "", "logs": ""},
            "debug_url": "",
            "tabs": [],
        }

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.post.return_value = start_response
            mock_requests.get.return_value = debug_response

            NotteProvider().create_session("task_custom")

        assert "https://custom.notte.example/sessions/start" in mock_requests.post.call_args[0][0]

    def test_create_session_respects_env_knobs(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        monkeypatch.setenv("NOTTE_PROXIES", "false")
        monkeypatch.setenv("NOTTE_SOLVE_CAPTCHAS", "true")
        monkeypatch.setenv("NOTTE_TIMEOUT_MINUTES", "30")
        from tools.browser_providers.notte import NotteProvider

        start_response = Mock()
        start_response.ok = True
        start_response.json.return_value = {"session_id": "sess_knobs"}

        debug_response = Mock()
        debug_response.ok = True
        debug_response.json.return_value = {
            "ws": {"cdp": "wss://cdp.notte.cc/sess_knobs", "recording": "", "logs": ""},
            "debug_url": "",
            "tabs": [],
        }

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.post.return_value = start_response
            mock_requests.get.return_value = debug_response

            result = NotteProvider().create_session("task_knobs")

        payload = mock_requests.post.call_args[1]["json"]
        assert "proxies" not in payload
        assert payload["solve_captchas"] is True
        assert payload["timeout_minutes"] == 30
        assert result["features"]["proxies"] is False
        assert result["features"]["solve_captchas"] is True

    def test_create_session_raises_on_start_failure(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        response = Mock()
        response.ok = False
        response.status_code = 401
        response.text = "Unauthorized"

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.post.return_value = response
            with pytest.raises(RuntimeError, match="Failed to create Notte session"):
                NotteProvider().create_session("task_fail")

    def test_create_session_raises_on_debug_failure(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        start_response = Mock()
        start_response.ok = True
        start_response.json.return_value = {"session_id": "sess_debug_fail"}

        debug_response = Mock()
        debug_response.ok = False
        debug_response.status_code = 500
        debug_response.text = "Internal Server Error"

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.post.return_value = start_response
            mock_requests.get.return_value = debug_response
            mock_requests.delete.return_value = Mock(status_code=200)

            with pytest.raises(RuntimeError, match="Failed to get Notte session CDP URL"):
                NotteProvider().create_session("task_debug_fail")

            # Verify emergency cleanup was attempted
            mock_requests.delete.assert_called_once()
            assert "/sessions/sess_debug_fail/stop" in mock_requests.delete.call_args[0][0]

    def test_create_session_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("NOTTE_API_KEY", raising=False)
        from tools.browser_providers.notte import NotteProvider

        with pytest.raises(ValueError, match="NOTTE_API_KEY"):
            NotteProvider().create_session("task_no_key")


class TestNotteCloseSession:
    def test_close_session_success(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        response = Mock()
        response.status_code = 200

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.delete.return_value = response
            assert NotteProvider().close_session("sess_close") is True

        assert "/sessions/sess_close/stop" in mock_requests.delete.call_args[0][0]

    def test_close_session_failure(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        response = Mock()
        response.status_code = 404
        response.text = "Session not found"

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.delete.return_value = response
            assert NotteProvider().close_session("sess_gone") is False

    def test_close_session_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("NOTTE_API_KEY", raising=False)
        from tools.browser_providers.notte import NotteProvider

        assert NotteProvider().close_session("sess_no_key") is False

    def test_close_session_network_error(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.delete.side_effect = ConnectionError("network down")
            assert NotteProvider().close_session("sess_net_err") is False


class TestNotteEmergencyCleanup:
    def test_emergency_cleanup_does_not_raise(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.delete.side_effect = Exception("total failure")
            # Must not raise
            NotteProvider().emergency_cleanup("sess_emergency")

    def test_emergency_cleanup_without_credentials(self, monkeypatch):
        monkeypatch.delenv("NOTTE_API_KEY", raising=False)
        from tools.browser_providers.notte import NotteProvider

        # Must not raise
        NotteProvider().emergency_cleanup("sess_no_creds")

    def test_emergency_cleanup_calls_stop(self, monkeypatch):
        monkeypatch.setenv("NOTTE_API_KEY", "nk-test")
        from tools.browser_providers.notte import NotteProvider

        response = Mock()
        response.status_code = 200

        with patch("tools.browser_providers.notte.requests") as mock_requests:
            mock_requests.delete.return_value = response
            NotteProvider().emergency_cleanup("sess_cleanup")

        assert "/sessions/sess_cleanup/stop" in mock_requests.delete.call_args[0][0]
        # Emergency cleanup uses shorter timeout
        assert mock_requests.delete.call_args[1]["timeout"] == 5


class TestNotteProviderRegistry:
    def test_notte_in_provider_registry(self):
        from tools.browser_tool import _PROVIDER_REGISTRY
        from tools.browser_providers.notte import NotteProvider

        assert "notte" in _PROVIDER_REGISTRY
        assert _PROVIDER_REGISTRY["notte"] is NotteProvider
