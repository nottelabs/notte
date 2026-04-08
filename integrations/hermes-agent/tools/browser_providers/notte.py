"""Notte cloud browser provider."""

import logging
import os
import uuid
from typing import Any, Dict, Optional

import requests

from tools.browser_providers.base import CloudBrowserProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.notte.cc"
_DEFAULT_TIMEOUT_MINUTES = 15


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

    def create_session(self, task_id: str) -> Dict[str, object]:
        config = self._get_config()

        enable_proxies = os.environ.get("NOTTE_PROXIES", "true").lower() != "false"
        enable_captchas = os.environ.get("NOTTE_SOLVE_CAPTCHAS", "false").lower() == "true"
        timeout_minutes = int(os.environ.get("NOTTE_TIMEOUT_MINUTES", str(_DEFAULT_TIMEOUT_MINUTES)))

        payload: Dict[str, object] = {
            "headless": True,
            "timeout_minutes": timeout_minutes,
        }
        if enable_proxies:
            payload["proxies"] = True
        if enable_captchas:
            payload["solve_captchas"] = True

        features_enabled: Dict[str, object] = {
            "proxies": enable_proxies,
            "solve_captchas": enable_captchas,
            "stealth": True,
        }

        # Step 1: Create session
        headers = self._headers(config)
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
        notte_session_id = session_data["session_id"]

        # Step 2: Get CDP WebSocket URL
        debug_response = requests.get(
            f"{config['base_url']}/sessions/{notte_session_id}/debug",
            headers=headers,
            timeout=60,
        )

        if not debug_response.ok:
            # Best-effort cleanup if we can't get the CDP URL
            self.emergency_cleanup(notte_session_id)
            raise RuntimeError(
                f"Failed to get Notte session CDP URL: "
                f"{debug_response.status_code} {debug_response.text}"
            )

        debug_data = debug_response.json()
        cdp_url = debug_data["ws"]["cdp"]

        session_name = f"hermes_{task_id}_{uuid.uuid4().hex[:8]}"

        feature_str = ", ".join(k for k, v in features_enabled.items() if v)
        logger.info("Created Notte session %s with features: %s", session_name, feature_str)

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
            logger.warning("Cannot close Notte session %s — missing credentials", session_id)
            return False

        try:
            response = requests.delete(
                f"{config['base_url']}/sessions/{session_id}/stop",
                headers=self._headers(config),
                timeout=10,
            )
            if response.status_code in (200, 201, 204):
                logger.debug("Successfully closed Notte session %s", session_id)
                return True
            else:
                logger.warning(
                    "Failed to close Notte session %s: HTTP %s",
                    session_id,
                    response.status_code,
                )
                return False

        except Exception as e:
            logger.error("Exception closing Notte session %s: %s", session_id, e)
            return False

    def emergency_cleanup(self, session_id: str) -> None:
        config = self._get_config_or_none()
        if config is None:
            logger.warning("Cannot emergency-cleanup Notte session %s — missing credentials", session_id)
            return
        try:
            requests.delete(
                f"{config['base_url']}/sessions/{session_id}/stop",
                headers=self._headers(config),
                timeout=5,
            )
        except Exception as e:
            logger.debug("Emergency cleanup failed for Notte session %s: %s", session_id, e)
