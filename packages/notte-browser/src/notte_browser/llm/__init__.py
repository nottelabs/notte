"""Optional LLM support for notte-browser, used for structured data extraction.

Install it with `pip install 'notte-browser[llm]'`.
"""

try:
    import litellm as _litellm  # noqa: F401  # pyright: ignore[reportUnusedImport]
except ImportError as e:
    raise ImportError(
        "Structured scraping with `instructions` or `response_format` on a local session needs the LLM extra. "
        + "Install it with `pip install 'notte-browser[llm]'` (or `pip install 'notte[llm]'`)."
    ) from e
