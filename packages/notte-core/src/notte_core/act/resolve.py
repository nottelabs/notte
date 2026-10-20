"""Find the default decider: Jev when `TYPESAFE_API_KEY` is set, else an LLM, else a clear error.

The deciders live in the optional `notte-llm` package. It is looked up at call time so that
notte-core, notte-sdk and notte-browser never import it unless `act()` runs.
"""

import importlib

from notte_core.act.errors import DeciderNotAvailableError
from notte_core.act.types import Decider


def default_decider() -> Decider:
    """`notte_llm.act.default_decider()`: see `notte_llm.act` for the environment variables it reads.

    Raises `DeciderNotAvailableError` when `notte-llm` is not installed or nothing is configured.
    """
    try:
        module = importlib.import_module("notte_llm.act")
    except ImportError as e:
        raise DeciderNotAvailableError(missing_package=True) from e
    decider: Decider = module.default_decider()
    return decider


def close_decider(decider: Decider) -> None:
    """Release the connections of a decider that has a `close()` method (e.g. `JevDecider`)."""
    close = getattr(decider, "close", None)
    if callable(close):
        _ = close()
