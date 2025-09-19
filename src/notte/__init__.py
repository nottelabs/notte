import notte_core.actions as actions
from notte_agent import Agent, AgentFallback
from notte_browser.session import NotteSession as Session
from notte_core import check_notte_version, set_error_mode
from notte_core.common.config import LlmModel as models
from notte_core.common.config import config
from notte_sdk.client import NotteClient
from notte_sdk.client import NotteClient as Client

__version__ = check_notte_version("notte")

SessionScript = Session.script

__all__ = [
    "Client",
    "NotteClient",
    "Session",
    "SessionScript",
    "Agent",
    "AgentFallback",
    "set_error_mode",
    "models",
    "config",
    "actions",
]
