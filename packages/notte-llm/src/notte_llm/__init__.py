"""LLM support for Notte: the default structured extractor used by `scrape(instructions=..., response_format=...)`,
and the deciders of `session.act()` / `choose()` / `check()` (`JevDecider`, `LlmDecider`)."""

from notte_core import check_notte_version

from notte_llm.act import JevDecider, LlmDecider, LlmWriter, default_decider
from notte_llm.extractor import LlmExtractor

__version__ = check_notte_version("notte_llm")

__all__ = ["JevDecider", "LlmDecider", "LlmExtractor", "LlmWriter", "default_decider"]
