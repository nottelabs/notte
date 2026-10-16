"""Driver error handlers catch errors from either supported browser backend."""

import importlib

import pytest
from notte_browser.driver import error_types, timeout_error_types


@pytest.mark.parametrize("backend", ["playwright", "patchright"])
def test_error_types_catch_each_backend(backend: str) -> None:
    api = importlib.import_module(f"{backend}.async_api")
    with pytest.raises(error_types(), match="backend error"):
        raise api.Error("backend error")


@pytest.mark.parametrize("backend", ["playwright", "patchright"])
def test_timeout_error_types_catch_each_backend(backend: str) -> None:
    api = importlib.import_module(f"{backend}.async_api")
    with pytest.raises(timeout_error_types(), match="backend timeout"):
        raise api.TimeoutError("backend timeout")
    # A generic driver error must not be mistaken for a timeout.
    with pytest.raises(api.Error, match="not a timeout"):
        try:
            raise api.Error("not a timeout")
        except timeout_error_types():
            pytest.fail("A non-timeout error matched the timeout handler")
