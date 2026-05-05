"""Notte cloud browser provider."""

import logging
import os
import uuid
from typing import Any, Dict, Optional, TypedDict

import requests
from tools.browser_providers.base import CloudBrowserProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.notte.cc"
_DEFAULT_TIMEOUT_MINUTES = 15


class NotteFeatures(TypedDict):
    proxies: bool
    solve_captchas: bool


class NotteSession(TypedDict):
    session_name: str
    bb_session_id: str
    cdp_url: str
    features: NotteFeatures


class NotteProvider(CloudBrowserProvider):
    """Notte (https://notte.cc) cloud browser backend.

    Notte is an open-source web agent framework providing cloud browser
    infrastructure with built-in CAPTCHA solving, residential proxies, and
    stealth capabilities.

    Requires a ``NOTTE_API_KEY`` environment variable.  Get a free API key at
    https://console.notte.cc.
    """

    def provider_name(self) -> str:
        return "Notte"

    def is_configured(self) -> bool:
        return self._get_config_or_none() is not None

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _get_config_or_none(self) -> Optional[Dict[str, Any]]:
        api_key = os.environ.get("NOTTE_API_KEY")
        if api_key:
            return {
                "api_key": api_key,
                "base_url": os.environ.get("NOTTE_API_URL", _DEFAULT_BASE_URL).rstrip("/"),
            }
        return None

    def _get_config(self) -> Dict[str, Any]:
        config = self._get_config_or_none()
        if config is None:
            raise ValueError(
                "Notte requires a NOTTE_API_KEY environment variable. "
                "Get your key at https://console.notte.cc"
            )
        return config

    def _headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
            "x-notte-request-origin": "hermes-agent",
        }

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self, task_id: str) -> NotteSession:
        config = self._get_config()

        enable_proxies = os.environ.get("NOTTE_PROXIES", "true").lower() != "false"
        enable_captchas = os.environ.get("NOTTE_SOLVE_CAPTCHAS", "false").lower() == "true"

        raw_timeout = os.environ.get("NOTTE_TIMEOUT_MINUTES", str(_DEFAULT_TIMEOUT_MINUTES))
        try:
            timeout_minutes = int(raw_timeout)
        except ValueError:
            raise ValueError(
                f"NOTTE_TIMEOUT_MINUTES must be a positive integer, got: {raw_timeout!r}"
            )
        if timeout_minutes <= 0:
            raise ValueError(
                f"NOTTE_TIMEOUT_MINUTES must be a positive integer, got: {raw_timeout!r}"
            )

        payload: Dict[str, object] = {
            "headless": True,
            "timeout_minutes": timeout_minutes,
        }
        if enable_proxies:
            payload["proxies"] = True
        if enable_captchas:
            payload["solve_captchas"] = True

        features_enabled: NotteFeatures = {
            "proxies": enable_proxies,
            "solve_captchas": enable_captchas,
        }

        # Step 1: Create session
        headers = self._headers(config)
        notte_session_id = None
        try:
            response = requests.post(
                f"{config['base_url']}/sessions/start",
                headers=headers,
                json=payload,
                timeout=60,
            )

            if not response.ok:
                raise RuntimeError(
                    f"Failed to create Notte session: "
                    f"{response.status_code} {response.text}"
                )

            session_data = response.json()
            notte_session_id = session_data.get("session_id")
            if not isinstance(notte_session_id, str) or not notte_session_id:
                raise RuntimeError(
                    f"Notte API returned unexpected response (missing 'session_id'): "
                    f"{response.text}"
                )

            # Step 2: Get CDP WebSocket URL
            debug_response = requests.get(
                f"{config['base_url']}/sessions/{notte_session_id}/debug",
                headers=headers,
                timeout=60,
            )

            if not debug_response.ok:
                raise RuntimeError(
                    f"Failed to get Notte session CDP URL: "
                    f"{debug_response.status_code} {debug_response.text}"
                )

            debug_data = debug_response.json()
            cdp_url = debug_data.get("ws", {}).get("cdp")
            if not isinstance(cdp_url, str) or not cdp_url:
                raise RuntimeError(
                    f"Notte API returned unexpected debug response (missing 'ws.cdp'): "
                    f"{debug_response.text}"
                )
        except Exception:
            if notte_session_id:
                self.emergency_cleanup(notte_session_id)
            raise

        session_name = f"hermes_{task_id}_{uuid.uuid4().hex[:8]}"

        feature_str = ", ".join(k for k, v in features_enabled.items() if v)
        logger.info(
            "Created Notte session %s with features: %s",
            session_name, feature_str,
        )

        return {
            "session_name": session_name,
            "bb_session_id": notte_session_id,
            "cdp_url": cdp_url,
            "features": features_enabled,
        }

    def close_session(self, session_id: str) -> bool:
        try:
            config = self._get_config()
        except ValueError:
            logger.warning("Cannot close Notte session: missing credentials")
            return False

        try:
            response = requests.delete(
                f"{config['base_url']}/sessions/{session_id}/stop",
                headers=self._headers(config),
                timeout=10,
            )
            if response.status_code in (200, 201, 204):
                logger.debug("Successfully closed Notte session")
                return True
            else:
                logger.warning(
                    "Failed to close Notte session: HTTP %s",
                    response.status_code,
                )
                return False

        except Exception as e:
            logger.error("Exception closing Notte session: %s", e)
            return False

    def emergency_cleanup(self, session_id: str) -> None:
        config = self._get_config_or_none()
        if config is None:
            logger.warning("Cannot emergency-cleanup Notte session: missing credentials")
            return
        try:
            requests.delete(
                f"{config['base_url']}/sessions/{session_id}/stop",
                headers=self._headers(config),
                timeout=5,
            )
        except Exception as e:
            logger.debug(
                "Emergency cleanup failed for Notte session: %s",
                e,
            )
