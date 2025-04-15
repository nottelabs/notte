from notte_core import check_notte_version

from notte_agent.main import Agent

__version__ = check_notte_version("notte_agent")

__all__ = ["Agent"]
