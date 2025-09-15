"""Session management interfaces for Notte integrations.

This module provides various session managers for browser automation:
- NotteSessionManager: Core window management functionality
- AnchorSessionsManager: Anchor-based session management
- BrowserBaseSessionsManager: BrowserBase integration
- SteelSessionsManager: Steel browser integration
"""

from notte_integrations.sessions.anchor import AnchorSessionsManager as AnchorSession
from notte_integrations.sessions.browserbase import BrowserBaseSessionsManager as BrowserBaseSession
from notte_integrations.sessions.hyperbrowser import HyperBrowserSessionsManager as HyperBrowserSession
from notte_integrations.sessions.notte import NotteSessionsManager as NotteSession
from notte_integrations.sessions.steel import SteelSessionsManager as SteelSession

__all__ = [
    "NotteSession",
    "SteelSession",
    "BrowserBaseSession",
    "AnchorSession",
    "HyperBrowserSession",
]
