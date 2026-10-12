import importlib.util

# These tests exercise the optional `notte-browser[llm]` extra; skip them when it is not installed.
collect_ignore_glob = [] if importlib.util.find_spec("litellm") is not None else ["test_*.py"]
