"""LLM support for Notte: the default structured extractor used by `scrape(instructions=..., response_format=...)`."""

from notte_core import check_notte_version

from notte_llm.extractor import LlmExtractor

__version__ = check_notte_version("notte_llm")

__all__ = ["LlmExtractor"]
