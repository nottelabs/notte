"""Session management interfaces for Notte integrations.

This module provides various session managers for browser automation:
- NotteSessionManager: Core window management functionality
- AnchorSessionsManager: Anchor-based session management
- BrowserBaseSessionsManager: BrowserBase integration
- SteelSessionsManager: Steel browser integration
"""

from notte_integrations.sessions.anchor import AnchorSessionsManager
from notte_integrations.sessions.browserbase import BrowserBaseSessionsManager
from notte_integrations.sessions.hyperbrowser import HyperBrowserSessionsManager
from notte_integrations.sessions.notte import NotteSessionsManager
from notte_integrations.sessions.steel import SteelSessionsManager

__all__ = [
    "NotteSessionsManager",
    "SteelSessionsManager",
    "BrowserBaseSessionsManager",
    "AnchorSessionsManager",
    "HyperBrowserSessionsManager",
]
