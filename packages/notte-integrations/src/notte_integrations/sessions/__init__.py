"""Session management interfaces for Notte integrations.

This module provides various session managers for browser automation:
- NotteSessionManager: Core window management functionality
- AnchorSessionsManager: Anchor-based session management
- BrowserBaseSessionsManager: BrowserBase integration
- SteelSessionsManager: Steel browser integration
"""

from typing import Literal

from notte_browser.playwright import GlobalWindowManager
from notte_browser.playwright import WindowManager as LocalSessionsManager

from notte_integrations.sessions.anchor import AnchorSessionsManager
from notte_integrations.sessions.browserbase import BrowserBaseSessionsManager
from notte_integrations.sessions.hyperbrowser import HyperBrowserSessionsManager
from notte_integrations.sessions.notte import NotteSessionsManager
from notte_integrations.sessions.steel import SteelSessionsManager


def configure_sessions_manager(
    provider: Literal["local", "notte", "steel", "browserbase", "anchor", "hyperbrowser"],
) -> None:
    match provider:
        case "local":
            GlobalWindowManager.configure(LocalSessionsManager())
        case "notte":
            NotteSessionsManager.configure()
        case "steel":
            SteelSessionsManager.configure()
        case "browserbase":
            BrowserBaseSessionsManager.configure()
        case "anchor":
            AnchorSessionsManager.configure()
        case "hyperbrowser":
            HyperBrowserSessionsManager.configure()
        case _:  # pyright: ignore
            raise ValueError(f"Invalid session manager provider: {provider}")  # pyright: ignore


__all__ = [
    "NotteSessionsManager",
    "LocalSessionsManager",
    "SteelSessionsManager",
    "BrowserBaseSessionsManager",
    "AnchorSessionsManager",
    "HyperBrowserSessionsManager",
    "configure_sessions_manager",
]
