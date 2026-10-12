import importlib.util

# These tests exercise the notte-llm package (installed with `notte[llm]`); skip them when litellm is missing.
collect_ignore_glob = [] if importlib.util.find_spec("litellm") is not None else ["test_*.py"]
