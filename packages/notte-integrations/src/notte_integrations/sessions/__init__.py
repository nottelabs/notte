"""Session management interfaces for Notte integrations.

This module provides various session managers for browser automation:
- NotteSessionManager: Core window management functionality
- AnchorSessionsManager: Anchor-based session management
- BrowserBaseSessionsManager: BrowserBase integration
- SteelSessionsManager: Steel browser integration
"""

from typing import Literal

from notte_browser.playwright import GlobalWindowManager
from notte_browser.playwright import WindowManager as NotteSessionManager

from notte_integrations.sessions.anchor import AnchorSessionsManager
from notte_integrations.sessions.browserbase import BrowserBaseSessionsManager
from notte_integrations.sessions.steel import SteelSessionsManager


def configure_session_manager(provider: Literal["notte", "steel", "browserbase", "anchor"]) -> None:
    match provider:
        case "notte":
            GlobalWindowManager.configure(NotteSessionManager())
        case "steel":
            SteelSessionsManager.configure()
        case "browserbase":
            BrowserBaseSessionsManager.configure()
        case "anchor":
            AnchorSessionsManager.configure()
        case _:  # pyright: ignore
            raise ValueError(f"Invalid session manager provider: {provider}")  # pyright: ignore


__all__ = [
    "SteelSessionsManager",
    "BrowserBaseSessionsManager",
    "NotteSessionManager",
    "AnchorSessionsManager",
    "configure_session_manager",
]
